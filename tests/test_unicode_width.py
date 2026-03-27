# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Test Unicode character width handling, especially emojis."""

from pathlib import Path

import wcwidth

from markdown_table_fixer.models import TableCell
from markdown_table_fixer.table_fixer import FileFixer
from markdown_table_fixer.table_parser import TableParser


def test_emoji_display_width():
    """Test that emojis are counted as 2 characters wide."""
    # Emoji is 1 character in len() but displays as 2 characters wide
    cell_with_emoji = TableCell(content="✅", start_col=0, end_col=3)
    assert len("✅") == 1  # String length
    assert cell_with_emoji.display_width == 2  # Display width


def test_regular_text_display_width():
    """Test that regular ASCII text width matches length."""
    cell = TableCell(content="Hello", start_col=0, end_col=5)
    assert cell.display_width == 5


def test_mixed_emoji_text_display_width():
    """Test mixed emoji and text."""
    cell = TableCell(content="✅ Passed", start_col=0, end_col=9)
    # ✅ (2) + space (1) + Passed (6) = 9
    assert cell.display_width == 9


def test_multiple_emojis_display_width():
    """Test multiple emojis."""
    cell = TableCell(content="✅ ❌", start_col=0, end_col=5)
    # ✅ (2) + space (1) + ❌ (2) = 5
    assert cell.display_width == 5


def test_cell_with_whitespace():
    """Test that whitespace is properly stripped."""
    cell = TableCell(content="  ✅ Test  ", start_col=0, end_col=11)
    # After strip: ✅ (2) + space (1) + Test (4) = 7
    assert cell.display_width == 7


def _display_pipe_positions(line: str) -> list[int]:
    """Get display-column positions of pipe characters in a line.

    Uses wcswidth on the prefix up to each pipe to stay consistent
    with the production width logic in TableCell.display_width.
    """
    positions: list[int] = []
    for i, ch in enumerate(line):
        if ch == "|":
            prefix = line[:i]
            w = wcwidth.wcswidth(prefix)
            # Fall back to len() if wcswidth returns -1 (unprintable chars)
            positions.append(w if w >= 0 else len(prefix))
    return positions


def test_table_with_emojis_alignment(tmp_path: Path) -> None:
    """Test that tables with emojis are properly aligned."""
    markdown_content = """
| Feature | Status |
|---------|--------|
| JSON    | ✅ Yes  |
| YAML    | ✅ Yes  |
| XML     | ❌ No   |
"""

    test_file = tmp_path / "test_emoji.md"
    test_file.write_text(markdown_content.strip(), encoding="utf-8")

    parser = TableParser(test_file)
    tables = parser.parse_file()
    fixer = FileFixer(test_file)
    result = fixer.fix_file(tables)

    # Should fix the table
    assert result.total_tables == 1

    # Read the fixed content
    fixed_content = test_file.read_text(encoding="utf-8")
    lines = fixed_content.split("\n")

    # Filter to table rows only (skip MD060 comments and blank lines)
    table_rows = [line for line in lines if line.startswith("|")]

    # Should have header + separator + 3 data rows = 5 table rows
    assert len(table_rows) >= 5
    data_rows = table_rows[2:]  # Skip header and separator

    # Extract display-width pipe positions for each data row
    pipe_positions = [_display_pipe_positions(row) for row in data_rows]

    # All rows should have pipes at the same display positions
    assert pipe_positions[0] == pipe_positions[1] == pipe_positions[2], (
        f"Pipes not aligned:\n"
        f"Row 1: {pipe_positions[0]}\n"
        f"Row 2: {pipe_positions[1]}\n"
        f"Row 3: {pipe_positions[2]}\n"
        f"Content:\n{fixed_content}"
    )


def test_complex_emoji_table(tmp_path: Path) -> None:
    """Test a more complex table with various emojis."""
    markdown_content = """
| Tool | Purpose | Status |
|------|---------|--------|
| `jq` | JSON parsing | ✅ Available |
| `yq` | YAML parsing | ⚠️ Needs install |
| `sed` | Text editing | ✅ Built-in |
"""

    test_file = tmp_path / "test_complex.md"
    test_file.write_text(markdown_content.strip(), encoding="utf-8")

    parser = TableParser(test_file)
    tables = parser.parse_file()
    fixer = FileFixer(test_file)
    result = fixer.fix_file(tables)

    assert result.total_tables == 1

    # Read the fixed content
    fixed_content = test_file.read_text(encoding="utf-8")
    lines = fixed_content.split("\n")

    # Filter to table rows only (skip MD060 comments and blank lines)
    table_rows = [line for line in lines if line.startswith("|")]

    # Check that all table rows have the same number of pipes
    for i, line in enumerate(table_rows, start=1):
        pipe_count = line.count("|")
        # Should have 4 pipes (3 columns = 4 pipes including borders)
        assert pipe_count == 4, f"Table row {i} has {pipe_count} pipes: {line}"

    # Extract display-width pipe positions for data rows
    data_rows = table_rows[2:]  # Skip header and separator
    pipe_positions = [_display_pipe_positions(row) for row in data_rows]

    # All rows should have pipes at the same display positions
    assert pipe_positions[0] == pipe_positions[1] == pipe_positions[2], (
        f"Pipes not aligned in complex table:\n{fixed_content}"
    )


def test_emoji_with_code_blocks():
    """Test that emojis work correctly with code blocks."""
    cell = TableCell(content="✅ `metadata_json`", start_col=0, end_col=20)
    # ✅ (2) + space (1) + `metadata_json` (15) = 18
    assert cell.display_width == 18


def test_various_unicode_characters():
    """Test various Unicode characters that have different widths."""
    test_cases = [
        ("★", 1),  # Black star - narrow (wcwidth returns 1)
        ("→", 1),  # Rightwards arrow - narrow
        ("中文", 4),  # Chinese characters - 2 each
        ("Hello", 5),  # Regular ASCII
        ("café", 4),  # With accented character
        ("🚀", 2),  # Rocket emoji
    ]

    for content, expected_width in test_cases:
        cell = TableCell(content=content, start_col=0, end_col=len(content))
        assert cell.display_width == expected_width, (
            f"'{content}' should have display width {expected_width}, "
            f"got {cell.display_width}"
        )


def test_non_printable_characters_fallback():
    """Test that non-printable characters fall back to len()."""
    # Control characters and other non-printable characters
    # wcwidth.wcswidth returns -1 for these
    cell = TableCell(content="\x00\x01\x02", start_col=0, end_col=3)
    # Should fall back to len()
    assert cell.display_width == 3


def test_html_entity_decoding():
    """Test that HTML entities are properly decoded before width calculation."""
    # Test numeric entity for pipe character
    cell = TableCell(content="&#124;", start_col=0, end_col=6)
    # &#124; = | which has width 1
    assert cell.display_width == 1

    # Test named entity
    cell = TableCell(content="&lt;", start_col=0, end_col=4)
    # &lt; = < which has width 1
    assert cell.display_width == 1

    # Test hexadecimal entity for emoji (grinning face)
    cell = TableCell(content="&#x1F600;", start_col=0, end_col=9)
    # &#x1F600; = 😀 which has width 2
    assert cell.display_width == 2

    # Test decimal entity for emoji (grinning face)
    cell = TableCell(content="&#128512;", start_col=0, end_col=9)
    # &#128512; = 😀 which has width 2
    assert cell.display_width == 2

    # Test mixed content with entities and regular text
    cell = TableCell(content="Status: &#x2705;", start_col=0, end_col=16)
    # "Status: " (8) + &#x2705; = ✅ (2) = 10
    assert cell.display_width == 10

    # Test multiple entities
    cell = TableCell(content="&#x2705; &#x274C;", start_col=0, end_col=17)
    # &#x2705; = ✅ (2) + space (1) + &#x274C; = ❌ (2) = 5
    assert cell.display_width == 5


def test_html_entity_with_regular_text():
    """Test HTML entities mixed with regular ASCII text."""
    cell = TableCell(content="Test &amp; Example", start_col=0, end_col=18)
    # "Test " (5) + &amp; = & (1) + " Example" (8) = 14
    assert cell.display_width == 14

    # Test entity at the beginning
    cell = TableCell(content="&quot;Hello&quot;", start_col=0, end_col=18)
    # &quot; = " (1) + "Hello" (5) + &quot; = " (1) = 7
    assert cell.display_width == 7


def test_html_entity_chinese_characters():
    """Test HTML entities for wide characters like Chinese."""
    # Chinese character (中) via numeric entity
    cell = TableCell(content="&#20013;", start_col=0, end_col=8)
    # &#20013; = 中 which has width 2
    assert cell.display_width == 2

    # Mix of entity and regular Chinese character
    cell = TableCell(content="&#20013;文", start_col=0, end_col=11)
    # &#20013; = 中 (2) + 文 (2) = 4
    assert cell.display_width == 4
