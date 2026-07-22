# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Parser for markdown tables."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from .exceptions import TableParseError
from .models import MarkdownTable, TableCell, TableRow


class TableParser:
    """Parse markdown tables from files."""

    # Regex to detect lines that look like table rows
    TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
    # Regex for separator rows (e.g., | --- | --- |)
    # Must contain at least one dash, and only pipes, dashes, colons, and spaces
    SEPARATOR_PATTERN = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")

    def __init__(self, file_path: Path):
        """Initialize parser with file path.

        Args:
            file_path: Path to the markdown file
        """
        self.file_path = file_path

    def parse_file(self) -> list[MarkdownTable]:
        """Parse all tables from the file.

        Returns:
            List of parsed tables

        Raises:
            TableParseError: If file cannot be read or parsed
        """
        try:
            with open(self.file_path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            raise TableParseError(
                f"Cannot read file {self.file_path}: {e}"
            ) from e

        return self._find_and_parse_tables(lines)

    def _find_and_parse_tables(self, lines: list[str]) -> list[MarkdownTable]:
        """Find and parse all tables in the lines.

        Args:
            lines: List of lines from the file

        Returns:
            List of parsed tables
        """
        tables: list[MarkdownTable] = []
        in_table = False
        table_start = -1
        table_rows: list[TableRow] = []

        for line_num, line in enumerate(lines, start=1):
            # Check if this line is part of a table
            if self._is_table_row(line):
                if not in_table:
                    # Start of a new table
                    in_table = True
                    table_start = line_num
                    table_rows = []

                row = self._parse_row(line, line_num)
                table_rows.append(row)
            # Not a table row
            elif in_table:
                # End of table
                if table_rows:
                    tables.append(
                        MarkdownTable(
                            rows=table_rows,
                            start_line=table_start,
                            end_line=line_num - 1,
                            file_path=self.file_path,
                        )
                    )
                in_table = False
                table_start = -1
                table_rows = []

        # Handle table at end of file
        if in_table and table_rows:
            tables.append(
                MarkdownTable(
                    rows=table_rows,
                    start_line=table_start,
                    end_line=len(lines),
                    file_path=self.file_path,
                )
            )

        return tables

    def _is_table_row(self, line: str) -> bool:
        """Check if a line is a table row.

        Args:
            line: Line to check

        Returns:
            True if line is a table row
        """
        return bool(self.TABLE_ROW_PATTERN.match(line))

    def _is_separator_row(self, line: str) -> bool:
        """Check if a line is a separator row.

        Args:
            line: Line to check

        Returns:
            True if line is a separator row
        """
        # Must match pattern and contain at least one dash
        if not self.SEPARATOR_PATTERN.match(line):
            return False
        # Verify it contains dashes (not just pipes and spaces)
        return "-" in line

    def _parse_row(self, line: str, line_num: int) -> TableRow:
        """Parse a single table row.

        Args:
            line: Line containing the row
            line_num: Line number in file

        Returns:
            Parsed table row
        """
        is_separator = self._is_separator_row(line)
        cells = self._parse_cells(line)

        return TableRow(
            cells=cells,
            line_number=line_num,
            raw_line=line.rstrip("\n\r"),
            is_separator=is_separator,
        )

    def _parse_cells(self, line: str) -> list[TableCell]:
        """Parse cells from a table row.

        Args:
            line: Line containing the row

        Returns:
            List of parsed cells
        """
        cells: list[TableCell] = []
        stripped = line.strip()

        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]

        # Split by pipe to get cells, but handle escaped pipes and HTML entities
        # We need to track column positions for alignment checking
        parts = self._split_by_unescaped_pipes(stripped)

        current_col = 1  # Start after first pipe
        for part in parts:
            content = part
            start_col = current_col
            end_col = current_col + len(part)

            cells.append(
                TableCell(content=content, start_col=start_col, end_col=end_col)
            )

            # Move to next column (account for pipe separator)
            current_col = end_col + 1

        return cells

    def _split_by_unescaped_pipes(self, text: str) -> list[str]:
        """Split text by pipes, but not escaped pipes or HTML entities.

        Args:
            text: Text to split

        Returns:
            List of cell contents
        """
        parts = []
        current = []
        i = 0

        while i < len(text):
            # Check for backslash-escaped pipe
            if i < len(text) - 1 and text[i : i + 2] == r"\|":
                # Keep the escaped pipe in the content
                current.append(text[i : i + 2])
                i += 2
            # Check for HTML entity for pipe (&#124;)
            elif i < len(text) - 5 and text[i : i + 6] == "&#124;":
                # Keep the HTML entity in the content
                current.append(text[i : i + 6])
                i += 6
            # Check for unescaped pipe (cell separator)
            elif text[i] == "|":
                # This is a cell separator
                parts.append("".join(current))
                current = []
                i += 1
            else:
                # Regular character
                current.append(text[i])
                i += 1

        # Add the last cell
        if (
            current or parts
        ):  # Include empty last cell if there were previous parts
            parts.append("".join(current))

        return parts


class MarkdownFileScanner:
    """Scanner for finding markdown files."""

    def __init__(self, root_path: Path):
        """Initialize scanner with root path.

        Args:
            root_path: Root directory to scan
        """
        self.root_path = root_path

    def find_markdown_files(self) -> list[Path]:
        """Find all markdown files in the directory tree.

        Returns:
            List of markdown file paths
        """
        if self.root_path.is_file():
            # Single file
            if self._is_markdown_file(self.root_path):
                return [self.root_path]
            return []

        # Directory - recursively find all markdown files
        markdown_files: list[Path] = []
        for path in self.root_path.rglob("*"):
            if path.is_file() and self._is_markdown_file(path):
                markdown_files.append(path)

        return sorted(markdown_files)

    def _is_markdown_file(self, path: Path) -> bool:
        """Check if a file is a markdown file.

        Args:
            path: File path to check

        Returns:
            True if file is markdown
        """
        return path.suffix.lower() in {".md", ".markdown", ".mdown", ".mkd"}
