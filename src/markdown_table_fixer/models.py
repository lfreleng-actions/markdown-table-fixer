# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Data models for markdown table fixer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import html
from pathlib import Path
from typing import Any

import wcwidth


# Inherit from (str, Enum) rather than enum.StrEnum to preserve Python
# 3.10 support (StrEnum was only added in 3.11; see requires-python).
class OutputFormat(str, Enum):  # noqa: UP042
    """Output format options."""

    TEXT = "text"
    JSON = "json"
    TABLE = "table"


# See OutputFormat above for why (str, Enum) is used instead of StrEnum.
class ViolationType(str, Enum):  # noqa: UP042
    """Types of table formatting violations."""

    MISALIGNED_PIPE = "misaligned_pipe"
    MISSING_SPACE_LEFT = "missing_space_left"
    MISSING_SPACE_RIGHT = "missing_space_right"
    EXTRA_SPACE_LEFT = "extra_space_left"
    EXTRA_SPACE_RIGHT = "extra_space_right"
    INCONSISTENT_ALIGNMENT = "inconsistent_alignment"
    MALFORMED_SEPARATOR = "malformed_separator"
    LINE_TOO_LONG = "line_too_long"

    def to_md_rule(self) -> str:
        """Convert violation type to markdownlint rule code.

        Returns:
            Markdownlint rule code (e.g., 'MD013', 'MD060')
        """
        if self == ViolationType.LINE_TOO_LONG:
            return "MD013"
        # All table formatting issues map to MD060 (table formatting)
        return "MD060"


@dataclass
class TableCell:
    """Represents a single table cell."""

    content: str
    start_col: int
    end_col: int

    @property
    def display_width(self) -> int:
        """Get the display width of the cell content.

        Uses wcwidth to properly calculate display width for Unicode characters,
        including emojis which display as 2 characters wide but count as 1 in len().
        Also handles HTML entities (e.g., &#124; for |, &#x1F600; for 😀).
        """
        stripped = self.content.strip()

        # Decode HTML entities to their actual characters
        # This properly handles both named entities (&lt;) and numeric entities (&#124;, &#x1F600;)
        # so that wide characters like emojis get their correct display width
        decoded = html.unescape(stripped)

        width = wcwidth.wcswidth(decoded)
        # wcswidth returns -1 if string contains non-printable characters
        # Fall back to len() in that case
        return width if width >= 0 else len(decoded)


@dataclass
class TableRow:
    """Represents a row in a markdown table."""

    cells: list[TableCell]
    line_number: int
    raw_line: str
    is_separator: bool = False

    @property
    def column_count(self) -> int:
        """Get the number of columns in this row."""
        return len(self.cells)


@dataclass
class MarkdownTable:
    """Represents a complete markdown table."""

    rows: list[TableRow]
    start_line: int
    end_line: int
    file_path: Path

    @property
    def column_count(self) -> int:
        """Get the number of columns in this table."""
        if not self.rows:
            return 0
        return max(row.column_count for row in self.rows)

    @property
    def has_header(self) -> bool:
        """Check if table has a header row."""
        return len(self.rows) >= 2 and self.rows[1].is_separator


@dataclass
class TableViolation:
    """Represents a table formatting violation."""

    violation_type: ViolationType
    line_number: int
    column: int
    message: str
    file_path: Path
    table_start_line: int = 0  # Line where the table starts

    @property
    def md_rule(self) -> str:
        """Get the markdownlint rule code for this violation.

        Returns:
            Markdownlint rule code (e.g., 'MD013', 'MD060')
        """
        return self.violation_type.to_md_rule()


@dataclass
class TableFix:
    """Represents a fix applied to a table."""

    file_path: Path
    start_line: int
    end_line: int
    original_content: str
    fixed_content: str
    violations_fixed: list[TableViolation]


@dataclass
class FileFixResult:
    """Results of fixing a single file.

    Tracks both structural table fixes and MD013 comment additions.
    """

    file_path: Path
    tables_fixed: int = 0  # Tables with structural fixes
    tables_with_md013: int = (
        0  # Tables that got MD013 comments (for line length)
    )
    tables_with_md060: int = 0  # Tables that got MD060 comments (for emojis)
    total_tables: int = 0  # Total tables processed in this file


@dataclass
class FileResult:
    """Results for a single markdown file."""

    file_path: Path
    tables_found: int = 0
    violations: list[TableViolation] = field(default_factory=list)
    fixes_applied: list[TableFix] = field(default_factory=list)
    error: str | None = None

    @property
    def has_violations(self) -> bool:
        """Check if file has any violations."""
        return len(self.violations) > 0

    @property
    def was_fixed(self) -> bool:
        """Check if any fixes were applied."""
        return len(self.fixes_applied) > 0

    def get_violations_by_rule(self) -> dict[str, int]:
        """Get violations grouped by markdownlint rule code.

        Returns:
            Dictionary mapping rule codes (e.g., 'MD013', 'MD060') to counts
        """
        rule_counts: dict[str, int] = {}
        for violation in self.violations:
            rule = violation.md_rule
            rule_counts[rule] = rule_counts.get(rule, 0) + 1
        return rule_counts


@dataclass
class ScanResult:
    """Overall scan results."""

    files_scanned: int = 0
    files_with_issues: int = 0
    files_fixed: int = 0
    total_violations: int = 0
    total_fixes: int = 0
    file_results: list[FileResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_file_result(self, result: FileResult) -> None:
        """Add a file result to the scan results."""
        self.file_results.append(result)
        self.files_scanned += 1

        if result.has_violations:
            self.files_with_issues += 1
            self.total_violations += len(result.violations)

        if result.was_fixed:
            self.files_fixed += 1
            self.total_fixes += len(result.fixes_applied)

        if result.error:
            self.errors.append(f"{result.file_path}: {result.error}")


@dataclass
class PRInfo:
    """Information about a GitHub pull request."""

    number: int
    title: str
    repository: str
    url: str
    author: str
    is_draft: bool
    head_ref: str
    head_sha: str
    base_ref: str
    mergeable: str
    merge_state_status: str


@dataclass
class BlockedPR:
    """A blocked pull request with blocking reasons."""

    pr_info: PRInfo
    blocking_reasons: list[str]
    has_markdown_issues: bool = False


@dataclass
class GitHubScanResult:
    """Results from scanning a GitHub organization."""

    organization: str
    repositories_scanned: int = 0
    total_prs: int = 0
    blocked_prs: list[BlockedPR] = field(default_factory=list)
    prs_fixed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class GitHubFixResult:
    """Result of fixing a PR."""

    pr_info: PRInfo
    success: bool
    message: str
    files_modified: list[Path] = field(default_factory=list)
    error: str | None = None


@dataclass
class CLIOptions:
    """Command-line interface options."""

    # Common options
    format: OutputFormat = OutputFormat.TEXT
    quiet: bool = False

    # Lint mode options
    path: Path = Path(".")
    fix: bool = False
    check: bool = False

    # GitHub mode options
    organization: str | None = None
    token: str | None = None
    threads: int | None = None
    dry_run: bool = False
    include_drafts: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert options to dictionary."""
        return {
            "format": self.format.value,
            "quiet": self.quiet,
            "path": str(self.path),
            "fix": self.fix,
            "check": self.check,
            "organization": self.organization,
            "threads": self.threads,
            "dry_run": self.dry_run,
            "include_drafts": self.include_drafts,
        }
