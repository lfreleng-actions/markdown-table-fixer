<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Markdown Table Fixer - Features

This document provides a comprehensive overview of the features implemented
in the markdown-table-fixer tool.

## Core Features

### 1. Table Detection and Parsing

The tool automatically detects and parses markdown tables in files:

- **Recursive File Scanning**: Scans directories recursively for markdown
  files (`.md`, `.markdown`, `.mdown`, `.mkd`)
- **Table Extraction**: Identifies and extracts all tables from markdown
  documents
- **Structure Analysis**: Parses table structure including headers,
  separator rows, and data rows
- **Cell Parsing**: Extracts individual cell content and tracks column
  positions

### 2. Validation and Issue Detection

Detects the following table formatting issues:

#### Alignment Issues

- **Misaligned Pipes**: Detects when pipe symbols (`|`) are not vertically
  aligned across rows
- **Inconsistent Column Count**: Identifies rows with different numbers of
  columns

#### Spacing Issues

- **Missing Left Space**: Detects cells without space after the opening
  pipe
- **Missing Right Space**: Detects cells without space before the closing
  pipe
- **Extra Spaces**: Identifies cells with more than one space on either
  side

#### Separator Row Issues

- **Malformed Separators**: Validates that separator rows (with dashes)
  have the correct format
- **Column Count Mismatch**: Ensures separator rows match header column
  count

### 3. Automatic Fixing

The tool can automatically fix detected issues:

- **Column Width Calculation**: Determines optimal width for each column
  based on content
- **Alignment Correction**: Aligns all pipes vertically for clean,
  readable tables
- **Spacing Normalization**: Ensures consistent spacing (one space on each
  side)
- **Separator Formatting**: Properly formats separator rows with correct
  alignment indicators (`:` for left/right/center)

### 4. Command-Line Interface

#### Lint Command

Scan and fix markdown files locally:

```bash
markdown-table-fixer lint [PATH] [OPTIONS]
```

Options:

- `--auto-fix`: Automatically fix issues
- `--format`: Output format (text, json)
- `--quiet, -q`: Suppress output except errors
- `--check`: Exit with error if issues found (CI mode)

#### GitHub Command (Placeholder)

Future feature for bulk-fixing tables in GitHub PRs:

```bash
markdown-table-fixer github ORG [OPTIONS]
```

### 5. Output Formats

#### Text Output

Rich, colorful terminal output with:

- Summary statistics
- Detailed violation reports
- File-by-file breakdown
- Progress indicators

#### JSON Output

Machine-readable JSON for integration with other tools:

```json
{
  "summary": {
    "files_scanned": 5,
    "files_with_issues": 2,
    "total_violations": 45
  },
  "files": [...]
}
```

### 6. Pre-commit Integration

Works seamlessly as a pre-commit hook:

```yaml
repos:
  - repo: https://github.com/lfreleng-actions/markdown-table-fixer
    rev: v1.0.0
    hooks:
      - id: markdown-table-fixer
```

Features:

- Automatic fixing before commits
- Fast execution
- Detailed error reporting
- Configurable arguments

### 7. Error Handling

Robust error handling with specific exception types:

- `FileAccessError`: File read/write issues
- `TableParseError`: Parsing failures
- `TableValidationError`: Validation problems
- `GitHubAPIError`: GitHub API issues (future)
- `AuthenticationError`: Authentication failures (future)
- `RateLimitError`: API rate limits (future)

## Technical Features

### Architecture

- **Modular Design**: Separate modules for parsing, validation, and fixing
- **Type Safety**: Full type hints throughout the codebase
- **Modern Python**: Uses Python 3.10+ features
- **Async Support**: Ready for async GitHub operations (future)

### Code Quality

- **Linting**: Ruff for code quality
- **Type Checking**: MyPy for static type analysis
- **Testing**: Pytest with 40%+ code coverage
- **Documentation**: Comprehensive docstrings

### Dependencies

Minimal, well-maintained dependencies:

- `typer`: CLI framework
- `rich`: Terminal formatting
- `httpx`: HTTP client (for future GitHub features)
- `pydantic`: Data validation
- `aiolimiter`: Rate limiting (for future GitHub features)
- `tenacity`: Retry logic (for future GitHub features)

## Example Transformations

### Before

```markdown
| Name | Type   | Description |
| ---- | ------ | ----------- |
| foo  | string | A value     |
```

### After

```markdown
| Name | Type   | Description |
| ---- | ------ | ----------- |
| foo  | string | A value     |
```

## Performance

- **Fast Scanning**: Efficiently processes large directory trees
- **Minimal Memory**: Processes files one at a time
- **Parallel Ready**: Architecture supports parallel processing for GitHub
  mode

## Compatibility

- **Markdownlint Compatible**: Fixes issues detected by markdownlint's
  MD060 rule
- **GitHub Flavored Markdown**: Supports GFM table syntax
- **Cross-platform**: Works on Linux, macOS, and Windows

## Limitations

### Current Limitations

- Does not handle tables within code blocks
- Does not support multi-line cells
- Does not preserve custom column alignment in all cases
- GitHub mode not yet implemented

### Future Enhancements

See CHANGELOG.md for planned features in upcoming releases.

## Testing

Comprehensive test suite covering:

- Table parsing with different formats
- Validation of different violation types
- File scanning and filtering
- Edge cases and error conditions

Run tests with:

```bash
pytest
```

## Documentation

- **README.md**: Quick start guide
- **CONTRIBUTING.md**: Contribution guidelines
- **CHANGELOG.md**: Version history
- **FEATURES.md**: This document
- **Inline Documentation**: Docstrings throughout the codebase

## Support

For issues, questions, or feature requests, please visit:
<https://github.com/lfreleng-actions/markdown-table-fixer/issues>
