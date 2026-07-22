# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Validator for markdown table formatting."""

from __future__ import annotations

from .models import MarkdownTable, TableRow, TableViolation, ViolationType


class TableValidator:
    """Validate markdown table formatting."""

    def __init__(
        self, table: MarkdownTable, max_line_length: int | None = None
    ):
        """Initialize validator with a table.

        Args:
            table: The table to validate
            max_line_length: Maximum line length for MD013 checking (None to skip)
        """
        self.table = table
        self.max_line_length = max_line_length

    def validate(self) -> list[TableViolation]:
        """Validate the table and return violations.

        Returns:
            List of violations found
        """
        violations: list[TableViolation] = []

        # Skip empty tables
        if not self.table.rows:
            return violations

        violations.extend(self._check_alignment())

        violations.extend(self._check_spacing())

        violations.extend(self._check_separator())

        # Check line length (MD013)
        if self.max_line_length is not None:
            violations.extend(self._check_line_length())

        return violations

    def _check_alignment(self) -> list[TableViolation]:
        """Check if table columns are properly aligned.

        Returns:
            List of alignment violations
        """
        violations: list[TableViolation] = []

        # Calculate expected pipe positions based on the widest content
        # in each column
        column_widths = self._calculate_column_widths()

        if not column_widths:
            return violations

        for row in self.table.rows:
            if len(row.cells) != len(column_widths):
                # Inconsistent column count
                violations.append(
                    TableViolation(
                        violation_type=ViolationType.INCONSISTENT_ALIGNMENT,
                        line_number=row.line_number,
                        column=0,
                        message=(
                            f"Row has {len(row.cells)} columns, expected "
                            f"{len(column_widths)}"
                        ),
                        file_path=self.table.file_path,
                        table_start_line=self.table.start_line,
                    )
                )
                continue

            # Check if pipes would align with expected positions
            expected_positions = self._calculate_pipe_positions(column_widths)
            actual_positions = self._get_actual_pipe_positions(row)

            for _idx, (expected, actual) in enumerate(
                zip(expected_positions, actual_positions, strict=False)
            ):
                if expected != actual:
                    violations.append(
                        TableViolation(
                            violation_type=ViolationType.MISALIGNED_PIPE,
                            line_number=row.line_number,
                            column=actual,
                            message=(
                                f"Pipe at column {actual} should be at "
                                f"column {expected}"
                            ),
                            file_path=self.table.file_path,
                            table_start_line=self.table.start_line,
                        )
                    )

        return violations

    def _check_spacing(self) -> list[TableViolation]:
        """Check if cells have proper spacing around content.

        Returns:
            List of spacing violations
        """
        violations: list[TableViolation] = []

        for row in self.table.rows:
            for idx, cell in enumerate(row.cells):
                content = cell.content

                if content and not content.startswith(" "):
                    violations.append(
                        TableViolation(
                            violation_type=ViolationType.MISSING_SPACE_LEFT,
                            line_number=row.line_number,
                            column=cell.start_col,
                            message=(
                                f"Cell in column {idx + 1} missing space "
                                "on left"
                            ),
                            file_path=self.table.file_path,
                            table_start_line=self.table.start_line,
                        )
                    )

                if content and not content.endswith(" "):
                    violations.append(
                        TableViolation(
                            violation_type=ViolationType.MISSING_SPACE_RIGHT,
                            line_number=row.line_number,
                            column=cell.end_col,
                            message=(
                                f"Cell in column {idx + 1} missing space "
                                "on right"
                            ),
                            file_path=self.table.file_path,
                            table_start_line=self.table.start_line,
                        )
                    )

                # Note: We don't check for "extra" spaces beyond the minimum 1 space
                # on each side, because padding is necessary for proper table alignment.
                # Tables need extra spaces to align pipes vertically across rows.

        return violations

    def _check_separator(self) -> list[TableViolation]:
        """Check if separator row is properly formatted.

        Returns:
            List of separator violations
        """
        violations: list[TableViolation] = []

        # Find separator row (should be second row if it exists)
        if len(self.table.rows) < 2:
            return violations

        separator_row = self.table.rows[1]
        if not separator_row.is_separator:
            return violations

        header_row = self.table.rows[0]
        if len(separator_row.cells) != len(header_row.cells):
            violations.append(
                TableViolation(
                    violation_type=ViolationType.MALFORMED_SEPARATOR,
                    line_number=separator_row.line_number,
                    column=0,
                    message=(
                        f"Separator has {len(separator_row.cells)} columns, "
                        f"header has {len(header_row.cells)}"
                    ),
                    file_path=self.table.file_path,
                    table_start_line=self.table.start_line,
                )
            )

        return violations

    def _calculate_column_widths(self) -> list[int]:
        """Calculate the maximum width needed for each column.

        For MD060 compliance, we calculate widths based on display width.
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
                    # Use display width for MD060 compliance (visual pipe alignment)
                    content_width = cell.display_width
                    max_width = max(max_width, content_width)
            widths.append(max_width)

        return widths

    def _calculate_pipe_positions(self, column_widths: list[int]) -> list[int]:
        """Calculate expected positions of pipes based on column widths.

        Args:
            column_widths: Width of each column (in display width units)

        Returns:
            List of pipe positions (in display width units)
        """
        positions: list[int] = [0]  # Starting pipe at position 0
        current_pos = 0

        for width in column_widths:
            # Each column: | space + content + space
            # Width of column = 1 (space) + content_width + 1 (space)
            column_total = width + 2
            current_pos += column_total + 1  # +1 for the pipe
            positions.append(current_pos)

        return positions

    def _get_actual_pipe_positions(self, row: TableRow) -> list[int]:
        """Get actual positions of pipes in a row.

        Args:
            row: The row to analyze

        Returns:
            List of pipe positions (in display width units)
        """
        import wcwidth

        positions: list[int] = []
        line = row.raw_line
        display_pos = 0

        for idx, char in enumerate(line):
            if char == "|":
                # Skip escaped pipes (preceded by an odd number of backslashes)
                backslash_count = 0
                j = idx - 1
                while j >= 0 and line[j] == "\\":
                    backslash_count += 1
                    j -= 1
                if backslash_count % 2 == 1:
                    # Odd number of backslashes means the pipe is escaped
                    display_pos += (
                        wcwidth.wcwidth(char)
                        if wcwidth.wcwidth(char) >= 0
                        else 1
                    )
                    continue
                positions.append(display_pos)

            # Update display position based on character width
            char_width = wcwidth.wcwidth(char)
            display_pos += char_width if char_width >= 0 else 1

        return positions

    def _check_line_length(self) -> list[TableViolation]:
        """Check if table rows exceed maximum line length (MD013).

        Returns:
            List of line length violations
        """
        violations: list[TableViolation] = []

        if self.max_line_length is None:
            return violations

        import wcwidth

        for row in self.table.rows:
            # Calculate display width of the line
            line_width = wcwidth.wcswidth(row.raw_line.rstrip())
            if line_width < 0:
                # Fall back to character count if wcswidth fails
                line_width = len(row.raw_line.rstrip())

            if line_width > self.max_line_length:
                violations.append(
                    TableViolation(
                        violation_type=ViolationType.LINE_TOO_LONG,
                        line_number=row.line_number,
                        column=0,
                        message=(
                            f"Line length {line_width} exceeds maximum "
                            f"{self.max_line_length} (MD013)"
                        ),
                        file_path=self.table.file_path,
                        table_start_line=self.table.start_line,
                    )
                )

        return violations
