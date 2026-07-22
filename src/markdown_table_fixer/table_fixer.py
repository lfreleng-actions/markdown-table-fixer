# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Fixer for markdown table formatting."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from .models import FileFixResult, MarkdownTable, TableFix, TableRow
from .table_validator import TableValidator

# Inclusive ``(low, high)`` code-point ranges used to detect emoji (and
# emoji-like wide characters) in table cells. The ranges are intentionally
# disjoint: the gaps between them (e.g. U+1F252-U+1F2FF, U+1F650-U+1F67F)
# are preserved so the matched set stays identical to the historical
# implementation. Do not merge or widen the ranges to close those gaps.
#
# Membership is tested with explicit integer comparisons rather than a
# regex character class. A character class containing several astral-plane
# (> U+FFFF) ranges triggers CodeQL's py/overly-large-range warning: the
# analyzer renders every astral escape as ``\ufffd``, so the distinct
# ranges all appear to collapse onto ``\ufffd-\ufffd`` and look like they
# overlap. Using ``ord`` comparisons sidesteps that false positive while
# preserving behaviour.
_EMOJI_CODEPOINT_RANGES: tuple[tuple[int, int], ...] = (
    (0x24C2, 0x1F251),  # enclosed chars, dingbats, flags
    (0x1F300, 0x1F64F),  # pictographs & emoticons
    (0x1F680, 0x1F6FF),  # transport & map symbols
    (0x1F900, 0x1FAFF),  # supplemental & extended pictographs
)


def _char_is_emoji(char: str) -> bool:
    """Return True if ``char`` falls within a known emoji code-point range.

    Args:
        char: A single character to test.

    Returns:
        True if the character's code point is within an emoji range.
    """
    code_point = ord(char)
    return any(
        low <= code_point <= high for low, high in _EMOJI_CODEPOINT_RANGES
    )


class TableFixer:
    """Fix markdown table formatting issues."""

    def __init__(self, table: MarkdownTable, max_line_length: int = 80):
        """Initialize fixer with a table.

        Args:
            table: The table to fix
            max_line_length: Maximum line length before adding MD013 disable
        """
        self.table = table
        self.max_line_length = max_line_length

    def fix(self) -> TableFix | None:
        """Fix the table formatting.

        Returns:
            TableFix if changes were made, None otherwise
        """
        # First validate to find violations
        # Don't pass max_line_length to validator here - MD013 violations are
        # handled by adding disable comments, not by reformatting the table
        validator = TableValidator(self.table)
        violations = validator.validate()

        if not violations:
            return None

        # Generate fixed table content
        fixed_lines = self._generate_fixed_table()

        original_lines = [row.raw_line for row in self.table.rows]
        original_content = "\n".join(original_lines)
        fixed_content = "\n".join(fixed_lines)

        if original_content == fixed_content:
            return None

        return TableFix(
            file_path=self.table.file_path,
            start_line=self.table.start_line,
            end_line=self.table.end_line,
            original_content=original_content,
            fixed_content=fixed_content,
            violations_fixed=violations,
        )

    def _generate_fixed_table(self) -> list[str]:
        """Generate properly formatted table lines.

        Returns:
            List of fixed table lines
        """
        if not self.table.rows:
            return []

        # Calculate column widths
        column_widths = self._calculate_column_widths()

        # Generate each row
        fixed_lines: list[str] = []
        for row in self.table.rows:
            if row.is_separator:
                fixed_line = self._format_separator_row(row, column_widths)
            else:
                fixed_line = self._format_data_row(row, column_widths)
            fixed_lines.append(fixed_line)

        return fixed_lines

    def _calculate_column_widths(self) -> list[int]:
        """Calculate the maximum width needed for each column.

        For MD060 compliance, we need to align pipes by display width.
        This uses display width (wcwidth), not character length, to properly
        handle Unicode characters like emojis that have different visual widths.

        Returns:
            List of column widths (in display width units)
        """
        if not self.table.rows:
            return []

        max_cols = max(len(row.cells) for row in self.table.rows)

        widths: list[int] = []
        for col_idx in range(max_cols):
            max_width = 0
            for row in self.table.rows:
                if col_idx < len(row.cells):
                    cell = row.cells[col_idx]
                    # For separator rows, use minimum width
                    if row.is_separator:
                        content_width = 3  # Minimum "---"
                    else:
                        # Use display width for MD060 compliance (visual pipe alignment)
                        content_width = cell.display_width
                    max_width = max(max_width, content_width)
            widths.append(max_width)

        return widths

    def _format_data_row(self, row: TableRow, column_widths: list[int]) -> str:
        """Format a data row with proper spacing and alignment.

        Args:
            row: The row to format
            column_widths: Width of each column (in display width units)

        Returns:
            Formatted row string
        """
        import wcwidth

        parts: list[str] = []

        for idx, cell in enumerate(row.cells):
            content = cell.content.strip()
            width = (
                column_widths[idx]
                if idx < len(column_widths)
                else cell.display_width
            )

            # Pad content to column width based on display width
            # This ensures pipes align by visual position (MD060 compliance)
            content_display_width = wcwidth.wcswidth(content)
            if content_display_width < 0:
                content_display_width = len(content)

            padding_needed = width - content_display_width
            padded = content + (" " * padding_needed)
            parts.append(f" {padded} ")

        return "|" + "|".join(parts) + "|"

    def _format_separator_row(
        self, row: TableRow, column_widths: list[int]
    ) -> str:
        """Format a separator row with proper dashes and alignment.

        Args:
            row: The separator row to format
            column_widths: Width of each column (in characters)

        Returns:
            Formatted separator row string
        """
        parts: list[str] = []

        for idx, cell in enumerate(row.cells):
            width = column_widths[idx] if idx < len(column_widths) else 3

            # Check for alignment indicators (: at start/end)
            content = cell.content.strip()
            left_align = content.startswith(":")
            right_align = content.endswith(":")

            # Generate separator with proper alignment indicators
            if left_align and right_align:
                # Center align
                separator = ":" + "-" * (width - 2) + ":"
            elif left_align:
                # Left align
                separator = ":" + "-" * (width - 1)
            elif right_align:
                # Right align
                separator = "-" * (width - 1) + ":"
            else:
                # Default (left align in most renderers)
                separator = "-" * width

            parts.append(f" {separator} ")

        return "|" + "|".join(parts) + "|"


class FileFixer:
    """Fix all tables in a markdown file."""

    def __init__(self, file_path: Path, max_line_length: int | None = None):
        """Initialize fixer with file path.

        Args:
            file_path: Path to the markdown file
            max_line_length: Maximum line length before adding MD013 disable
                           (None = auto-detect from markdownlint config, default 80)
        """
        self.file_path = file_path
        # Auto-detect line length from config if not specified
        self.max_line_length = (
            max_line_length
            if max_line_length is not None
            else self._get_md013_line_length()
        )
        self._md013_enabled = self._check_md013_enabled()
        self._md060_enabled = self._check_md060_enabled()

    def _remove_jsonc_comments(self, content: str) -> str:
        """Remove comments from JSONC content.

        This is a simple implementation that removes // comments while being
        aware of strings. It's not perfect but handles most common cases.

        Args:
            content: JSONC content string

        Returns:
            Content with comments removed
        """
        lines = []
        for line in content.split("\n"):
            # Track if we're inside a string
            in_string = False
            escape_next = False
            processed = []

            i = 0
            while i < len(line):
                char = line[i]

                if escape_next:
                    processed.append(char)
                    escape_next = False
                    i += 1
                    continue

                if char == "\\":
                    processed.append(char)
                    escape_next = True
                    i += 1
                    continue

                if char == '"':
                    in_string = not in_string
                    processed.append(char)
                    i += 1
                    continue

                # Check for comment start (only outside strings)
                if (
                    not in_string
                    and i < len(line) - 1
                    and line[i : i + 2] == "//"
                ):
                    # Rest of line is a comment
                    break

                processed.append(char)
                i += 1

            lines.append("".join(processed))

        return "\n".join(lines)

    def _load_markdownlint_config(
        self, config_path: Path, config_name: str
    ) -> object | None:
        """Load a markdownlint config file into a parsed object.

        Returns the parsed config, or None if the extension is unsupported.
        """
        with open(config_path, encoding="utf-8") as f:
            if config_name.endswith((".yaml", ".yml")):
                yaml_config: object = yaml.safe_load(f)
                # yaml.safe_load returns None for empty files
                return yaml_config if yaml_config is not None else {}
            if config_name.endswith((".json", ".jsonc", "rc")):
                content = f.read()
                if config_name.endswith(".jsonc"):
                    content = self._remove_jsonc_comments(content)
                json_config: object = json.loads(content)
                return json_config
        return None

    def _iter_markdownlint_configs(self) -> Iterator[object]:
        """Yield parsed markdownlint configs, walking up from the file.

        Config files are visited in ``config_names`` order within each
        directory, then the search moves up to the parent directory (up to
        five levels). Files that are missing, unsupported, or unreadable are
        skipped so callers only see successfully parsed configs.
        """
        current_dir = self.file_path.parent
        config_names = [
            ".markdownlint.json",
            ".markdownlint.jsonc",
            ".markdownlint.yaml",
            ".markdownlint.yml",
            ".markdownlintrc",
        ]

        # Search up to 5 levels up
        for _ in range(5):
            for config_name in config_names:
                config_path = current_dir / config_name
                if not config_path.exists():
                    continue
                try:
                    config = self._load_markdownlint_config(
                        config_path, config_name
                    )
                except (json.JSONDecodeError, yaml.YAMLError, OSError):
                    # If config can't be read, keep searching
                    continue
                if config is not None:
                    yield config

            # Move up one directory
            if current_dir.parent == current_dir:
                break  # Reached root
            current_dir = current_dir.parent

    def _check_rule_enabled(self, rule_name: str) -> bool:
        """Check if a markdownlint rule is enabled in config.

        Args:
            rule_name: Name of the rule (e.g., "MD013", "MD060")

        Returns:
            True if rule checking is enabled, False otherwise
        """
        # The first readable dict config found decides the outcome.
        # Skip configs that don't parse to a mapping (e.g. a YAML list)
        # so a usable dict config higher up the tree is not hidden.
        for config in self._iter_markdownlint_configs():
            if not isinstance(config, dict):
                continue
            if rule_name in config:
                # Explicitly disabled only when set to ``false``
                return config[rule_name] is not False
            # If not specified, assume enabled (markdownlint default)
            return True

        # No config found, assume rule is enabled by default
        return True

    def _check_md013_enabled(self) -> bool:
        """Check if MD013 is enabled in markdownlint config.

        Returns:
            True if MD013 checking is enabled, False otherwise
        """
        return self._check_rule_enabled("MD013")

    def _extract_md013_line_length(self, config: object) -> int | None:
        """Return the MD013 line_length from a config dict, if configured."""
        if not isinstance(config, dict):
            return None
        md013_config = config.get("MD013")
        if isinstance(md013_config, dict) and "line_length" in md013_config:
            line_length = md013_config["line_length"]
            if isinstance(line_length, int):
                return line_length
        return None

    def _get_md013_line_length(self) -> int:
        """Get MD013 line_length from markdownlint config.

        Returns:
            Configured line length, or 80 if not configured
        """
        for config in self._iter_markdownlint_configs():
            line_length = self._extract_md013_line_length(config)
            if line_length is not None:
                return line_length

        # No config found or line_length not specified, return default
        return 80

    def _check_md060_enabled(self) -> bool:
        """Check if MD060 is enabled in markdownlint config.

        Returns:
            True if MD060 checking is enabled, False otherwise
        """
        return self._check_rule_enabled("MD060")

    def _table_has_emojis(self, table: MarkdownTable) -> bool:
        """Check if table contains emoji characters.

        Emojis cause alignment issues because they take 1 character position
        but display as 2 characters wide, making MD060 compliance impossible.

        Args:
            table: The table to check

        Returns:
            True if table contains emojis
        """
        for row in table.rows:
            for cell in row.cells:
                if any(_char_is_emoji(char) for char in cell.content):
                    return True
        return False

    def _parse_markdownlint_comment(
        self, line: str, comment_type: str
    ) -> set[str]:
        """Parse markdownlint comment to extract rule names.

        Args:
            line: The line to parse
            comment_type: Either "disable" or "enable"

        Returns:
            Set of rule names found in the comment (e.g., {"MD013", "MD060"})
        """
        # Match markdownlint comments with word boundaries for rule names
        # Examples:
        #   <!-- markdownlint-disable MD013 MD060 -->
        #   <!-- markdownlint-enable MD013 -->
        pattern = rf"<!--\s*markdownlint-{comment_type}\s+(.*?)\s*-->"
        match = re.search(pattern, line)
        if not match:
            return set()

        rules_text = match.group(1)
        # Match MD followed by digits, using word boundaries to avoid false matches
        rule_pattern = r"\bMD\d+\b"
        rules = re.findall(rule_pattern, rules_text)
        return set(rules)

    def fix_file(
        self, tables: list[MarkdownTable], dry_run: bool = False
    ) -> FileFixResult:
        """Fix all tables in the file.

        Args:
            tables: List of tables to fix
            dry_run: If True, don't write changes to file

        Returns:
            FileFixResult with detailed breakdown of changes
        """
        fixes: list[TableFix] = []

        for table in tables:
            fixer = TableFixer(table, self.max_line_length)
            fix = fixer.fix()
            if fix:
                fixes.append(fix)

        # Calculate MD013 and MD060 counts (even in dry_run mode for reporting)
        md013_count, md060_count = self._calculate_md_comment_needs(
            fixes, tables
        )

        if not dry_run:
            # Apply fixes and add MD013 comments for all tables
            self._apply_fixes(fixes, tables)

        return FileFixResult(
            file_path=self.file_path,
            tables_fixed=len(fixes),
            tables_with_md013=md013_count,
            tables_with_md060=md060_count,
            total_tables=len(tables),
        )

    def _calculate_md_comment_needs(
        self, fixes: list[TableFix], all_tables: list[MarkdownTable]
    ) -> tuple[int, int]:
        """Calculate which tables need MD013/MD060 comments.

        Args:
            fixes: List of fixes to apply
            all_tables: All tables in the file

        Returns:
            Tuple of (md013_count, md060_count) - number of tables that need each type of comment
        """
        tables_needing_md013 = 0
        tables_needing_md060 = 0

        for table in all_tables:
            # Get the table content (either fixed or original)
            table_lines = []
            fix_for_table = None
            for fix in fixes:
                if (
                    fix.start_line == table.start_line
                    and fix.end_line == table.end_line
                ):
                    fix_for_table = fix
                    table_lines = fix.fixed_content.split("\n")
                    break

            # If no fix, use original lines
            if not fix_for_table:
                table_lines = [row.raw_line for row in table.rows]

            # Check if any line exceeds max_line_length
            max_len = (
                max(len(line.rstrip()) for line in table_lines)
                if table_lines
                else 0
            )
            if max_len > self.max_line_length:
                tables_needing_md013 += 1

            # Check if table has emojis (causes MD060 violations)
            if self._md060_enabled and self._table_has_emojis(table):
                tables_needing_md060 += 1

        return tables_needing_md013, tables_needing_md060

    def _apply_fixes(
        self, fixes: list[TableFix], all_tables: list[MarkdownTable]
    ) -> None:
        """Apply fixes to the file and add MD013 comments where needed.

        Args:
            fixes: List of fixes to apply
            all_tables: All tables in the file (for checking line lengths)
        """
        # Read the entire file
        with open(self.file_path, encoding="utf-8") as f:
            lines = f.readlines()

        tables_needing_md013, tables_needing_md060 = self._categorize_tables(
            fixes, all_tables
        )
        all_modifications = self._build_modifications(
            fixes, tables_needing_md013, tables_needing_md060
        )

        # Apply all modifications in reverse order to maintain line numbers
        # (only if there are modifications to apply)
        if not all_modifications:
            return

        for (
            start_line,
            end_line,
            content_lines,
            needs_md013,
            needs_md060,
        ) in sorted(all_modifications, key=lambda x: x[0], reverse=True):
            start_idx = start_line - 1
            end_idx = end_line

            # Prepare the lines to insert
            new_lines = [line + "\n" for line in content_lines]

            # Collect all disable/enable rules needed
            disable_rules = []
            if needs_md013 and self._md013_enabled:
                disable_rules.append("MD013")
            if needs_md060 and self._md060_enabled:
                disable_rules.append("MD060")

            # Add markdownlint comments if needed
            if disable_rules:
                self._insert_markdownlint_comments(
                    new_lines, lines, start_idx, end_idx, disable_rules
                )

            # Replace the section
            lines[start_idx:end_idx] = new_lines

        with open(self.file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _categorize_tables(
        self,
        fixes: list[TableFix],
        all_tables: list[MarkdownTable],
    ) -> tuple[
        dict[int, tuple[MarkdownTable, list[str]]],
        dict[int, tuple[MarkdownTable, list[str]]],
    ]:
        """Find tables needing MD013 (line length) and MD060 (emoji) comments.

        Returns a ``(tables_needing_md013, tables_needing_md060)`` tuple, each
        keyed by the table's start line.
        """
        tables_needing_md013: dict[int, tuple[MarkdownTable, list[str]]] = {}
        tables_needing_md060: dict[int, tuple[MarkdownTable, list[str]]] = {}

        for table in all_tables:
            # Get the table content (either fixed or original)
            table_lines: list[str] = []
            fix_for_table = None
            for fix in fixes:
                if (
                    fix.start_line == table.start_line
                    and fix.end_line == table.end_line
                ):
                    fix_for_table = fix
                    table_lines = fix.fixed_content.split("\n")
                    break

            # If no fix, use original lines
            if not fix_for_table:
                table_lines = [row.raw_line for row in table.rows]

            # Check if any line exceeds max_line_length
            max_len = (
                max(len(line.rstrip()) for line in table_lines)
                if table_lines
                else 0
            )
            if max_len > self.max_line_length:
                tables_needing_md013[table.start_line] = (table, table_lines)

            # Check if table has emojis (causes MD060 violations)
            if self._md060_enabled and self._table_has_emojis(table):
                tables_needing_md060[table.start_line] = (table, table_lines)

        return tables_needing_md013, tables_needing_md060

    def _build_modifications(
        self,
        fixes: list[TableFix],
        tables_needing_md013: dict[int, tuple[MarkdownTable, list[str]]],
        tables_needing_md060: dict[int, tuple[MarkdownTable, list[str]]],
    ) -> list[tuple[int, int, list[str], bool, bool]]:
        """Combine fixes and comment-only tables into one modification list."""
        # Each entry is (start_line, end_line, lines, needs_md013, needs_md060)
        all_modifications: list[tuple[int, int, list[str], bool, bool]] = []

        # Add fixes to modifications list
        for fix in fixes:
            fixed_lines = fix.fixed_content.split("\n")
            all_modifications.append(
                (
                    fix.start_line,
                    fix.end_line,
                    fixed_lines,
                    fix.start_line in tables_needing_md013,
                    fix.start_line in tables_needing_md060,
                )
            )

        # Add tables that need MD013 but have no fixes
        for start_line, (table, table_lines) in tables_needing_md013.items():
            # Check if already in fixes
            if not any(mod[0] == start_line for mod in all_modifications):
                all_modifications.append(
                    (
                        table.start_line,
                        table.end_line,
                        table_lines,
                        True,
                        start_line in tables_needing_md060,
                    )
                )

        # Add tables that need MD060 but have no fixes or MD013
        for start_line, (table, table_lines) in tables_needing_md060.items():
            # Check if already in fixes or MD013 list
            if not any(mod[0] == start_line for mod in all_modifications):
                all_modifications.append(
                    (table.start_line, table.end_line, table_lines, False, True)
                )

        return all_modifications

    def _insert_markdownlint_comments(
        self,
        new_lines: list[str],
        lines: list[str],
        start_idx: int,
        end_idx: int,
        disable_rules: list[str],
    ) -> None:
        """Wrap ``new_lines`` in markdownlint disable/enable comments in place.

        Existing disable/enable comments within three lines of the table are
        detected so duplicates are not added.
        """
        disable_comment = " ".join(disable_rules)

        # Check if disable comment already exists within 3 lines before table
        has_disable = False
        check_start = max(0, start_idx - 3)
        for i in range(check_start, start_idx):
            found_rules = self._parse_markdownlint_comment(lines[i], "disable")
            if all(rule in found_rules for rule in disable_rules):
                has_disable = True
                break

        # Check if enable comment already exists within 3 lines after table
        has_enable = False
        check_end = min(len(lines), end_idx + 3)
        for i in range(end_idx, check_end):
            found_rules = self._parse_markdownlint_comment(lines[i], "enable")
            if all(rule in found_rules for rule in disable_rules):
                has_enable = True
                break

        # Add disable comment if not present
        if not has_disable:
            # Check for blank line before table
            if start_idx > 0 and lines[start_idx - 1].strip():
                # No blank line, add both blank line and comment
                new_lines.insert(0, "\n")
                new_lines.insert(
                    1,
                    f"<!-- markdownlint-disable {disable_comment} -->\n",
                )
                new_lines.insert(2, "\n")
            else:
                # Blank line exists, just add comment
                new_lines.insert(
                    0,
                    f"<!-- markdownlint-disable {disable_comment} -->\n",
                )
                new_lines.insert(1, "\n")

        # Add enable comment if not present
        if not has_enable:
            # Always add blank line and enable comment
            new_lines.append("\n")
            new_lines.append(
                f"<!-- markdownlint-enable {disable_comment} -->\n"
            )
