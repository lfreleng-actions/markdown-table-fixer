<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Setup Guide

This guide covers different ways to set up and use markdown-table-fixer.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation Methods](#installation-methods)
- [Pre-commit Integration](#pre-commit-integration)
- [CI/CD Integration](#cicd-integration)
- [Development Setup](#development-setup)
- [Troubleshooting](#troubleshooting)

## Quick Start

The fastest way to get started:

```bash
# Install with pip
pip install markdown-table-fixer

# Run on current directory
markdown-table-fixer lint --auto-fix
```

## Installation Methods

### Using pip

```bash
pip install markdown-table-fixer
```

### Using uv (recommended for development)

```bash
uv pip install markdown-table-fixer
```

### From source

```bash
git clone https://github.com/lfit/markdown-table-fixer.git
cd markdown-table-fixer
pip install -e .
```

### In a virtual environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install
pip install markdown-table-fixer
```

## Pre-commit Integration

### Basic Setup

1. Add to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/lfit/markdown-table-fixer
    rev: v1.0.0  # Use latest version
    hooks:
      - id: markdown-table-fixer
```

1. Install the hooks:

```bash
pre-commit install
```

1. Run on all files (optional):

```bash
pre-commit run markdown-table-fixer --all-files
```

### Available Hooks

#### markdown-table-fixer (auto-fix)

Automatically fixes table formatting issues:

```yaml
- id: markdown-table-fixer
  # Optional: customize behavior
  args: [lint, ., --auto-fix]
```

#### markdown-table-fixer-check (validation)

Checks for issues without fixing (useful for CI):

```yaml
- id: markdown-table-fixer-check
  # Fails if issues found, doesn't change files
```

### Advanced Configuration

#### Limit to specific directories

```yaml
- id: markdown-table-fixer
  files: ^docs/.*\.md$  # Docs directory
```

#### Run on specific file types

```yaml
- id: markdown-table-fixer
  files: '\.md$|\.markdown$'  # Default behavior
```

#### Skip specific files

```yaml
- id: markdown-table-fixer
  exclude: ^vendor/|^third_party/
```

## CI/CD Integration

### GitHub Actions

Create `.github/workflows/markdown-tables.yaml`:

```yaml
name: Markdown Tables

on:
  pull_request:
    paths:
      - '**.md'
      - '**.markdown'

jobs:
  check-tables:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install markdown-table-fixer
        run: pip install markdown-table-fixer

      - name: Check markdown tables
        run: markdown-table-fixer lint . --check
```

### GitLab CI

Add to `.gitlab-ci.yml`:

```yaml
markdown-tables:
  image: python:3.11
  script:
    - pip install markdown-table-fixer
    - markdown-table-fixer lint . --check
  only:
    changes:
      - "**/*.md"
```

### Jenkins

Add to `Jenkinsfile`:

```groovy
stage('Check Markdown Tables') {
    steps {
        sh '''
            pip install markdown-table-fixer
            markdown-table-fixer lint . --check
        '''
    }
}
```

### CircleCI

Add to `.circleci/config.yml`:

```yaml
jobs:
  markdown-tables:
    docker:
      - image: python:3.11
    steps:
      - checkout
      - run:
          name: Install markdown-table-fixer
          command: pip install markdown-table-fixer
      - run:
          name: Check tables
          command: markdown-table-fixer lint . --check
```

## Development Setup

### Prerequisites

- Python 3.10 or higher
- Git
- uv (recommended) or pip

### Full Development Environment

```bash
# Clone the repository
git clone https://github.com/lfit/markdown-table-fixer.git
cd markdown-table-fixer

# Create virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with development dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=markdown_table_fixer

# Run specific test file
pytest tests/test_table_parser.py -v

# Run with verbose output
pytest -vv
```

### Code Quality Checks

```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Run specific checks
ruff check src tests
ruff format --check src tests
mypy src
```

### Building the Package

```bash
# Install build tools
pip install build

# Build source distribution and wheel
python -m build

# Check the distribution
pip install twine
twine check dist/*
```

## Troubleshooting

### Pre-commit hook not found

**Problem**: `[ERROR] markdown-table-fixer is not installed`

**Solution**: Update pre-commit hooks:

```bash
pre-commit autoupdate
pre-commit clean
pre-commit install
```

### Import errors

**Problem**: `ModuleNotFoundError: No module named 'markdown_table_fixer'`

**Solution**: Install the package first:

```bash
pip install markdown-table-fixer
# Or for development:
pip install -e .
```

### Tables not getting fixed

**Problem**: Tool detects issues but doesn't fix them

**Solution**: Use the `--auto-fix` flag:

```bash
markdown-table-fixer lint --auto-fix
```

Or use the auto-fix pre-commit hook:

```yaml
- id: markdown-table-fixer  # Not markdown-table-fixer-check
```

### Performance issues

**Problem**: Tool is slow on large repositories

**Solutions**:

1. Limit to specific directories:

   ```bash
   markdown-table-fixer lint docs/
   ```

2. Use file filtering in pre-commit:

   ```yaml
   files: ^docs/.*\.md$
   ```

3. Exclude generated or vendor files:

   ```yaml
   exclude: ^(vendor|node_modules)/
   ```

### Version conflicts

**Problem**: Dependency conflicts with other packages

**Solution**: Use a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install markdown-table-fixer
```

### Pre-commit runs but doesn't fix

**Problem**: Pre-commit shows "Passed" but tables aren't fixed

**Check**:

1. Verify you're using the fix hook (not check):

   ```yaml
   - id: markdown-table-fixer  # Correct
   # Not: markdown-table-fixer-check
   ```

2. Check hook arguments:

   ```yaml
   - id: markdown-table-fixer
     args: [lint, ., --auto-fix]  # Ensure --auto-fix is present
   ```

3. Run manually to see detailed output:

   ```bash
   markdown-table-fixer lint . --auto-fix
   ```

## Platform-Specific Notes

### Windows

Use backslashes or forward slashes in paths:

```bash
markdown-table-fixer lint docs\
# Or
markdown-table-fixer lint docs/
```

Activate virtual environment:

```bash
.venv\Scripts\activate
```

### macOS

If you encounter SSL errors, update certificates:

```bash
pip install --upgrade certifi
```

### Linux

Ensure Python 3.10+ is available:

```bash
python3 --version
# If needed, install:
sudo apt-get install python3.11  # Ubuntu/Debian
```

## Getting Help

If you encounter issues not covered here:

1. Check the [GitHub Issues](https://github.com/lfit/markdown-table-fixer/issues)
2. Review the [README](README.md) and [CONTRIBUTING](CONTRIBUTING.md)
3. Open a new issue with:
   - Your operating system and Python version
   - The command you ran
   - The error message or unexpected behavior
   - A minimal example that reproduces the issue

## Next Steps

- Review [FEATURES.md](FEATURES.md) for complete feature list
- Read [CONTRIBUTING.md](CONTRIBUTING.md) if you want to contribute
- Check [CHANGELOG.md](CHANGELOG.md) for version history
