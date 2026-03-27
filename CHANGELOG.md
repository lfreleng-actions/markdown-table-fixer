<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Changelog

All notable changes to this project will appear in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New `--pr-changes-only` flag to limit processing to files changed in the PR
- Initial release of markdown-table-fixer
- Lint mode for scanning and fixing markdown table formatting issues
- Support for detecting misaligned pipes in markdown tables
- Support for detecting missing/extra spacing around table cells
- Support for detecting malformed separator rows
- Automatic fixing of table formatting issues
- Text and JSON output formats
- Pre-commit hook integration
- Comprehensive test suite

### Changed

- **BREAKING**: API method now scans all markdown files by default
  (the API method used to scan only files changed in the PR)
  - Both API and Git methods now have consistent behavior
  - Use `--pr-changes-only` flag to restore the old PR-changes-only API behavior
- Git method can now limit scope to PR changes with `--pr-changes-only` flag
- CLI with Typer for user-friendly interface
- Rich terminal output with progress tracking
- File scanner for recursive markdown file discovery
- Table parser for extracting tables from markdown files
- Table validator for detecting formatting violations
- Table fixer for automatically correcting issues

### GitHub Mode (Planned)

- Scan GitHub organizations for blocked pull requests
- Automatically fix markdown table issues in PRs
- Parallel processing of repositories
- Commit signing and force-push support
- Integration with pre-commit.ci failures

## [0.1.0] - 2025-01-24

### Initial Release

- Initial project structure
- Core table parsing functionality
- Core table validation functionality
- Core table fixing functionality
- Command-line interface with lint subcommand
- Basic test coverage
- Pre-commit configuration
- Documentation (README, CONTRIBUTING)

[Unreleased]: https://github.com/lfit/markdown-table-fixer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lfit/markdown-table-fixer/releases/tag/v0.1.0
