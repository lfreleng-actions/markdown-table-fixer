<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Contributing to Markdown Table Fixer

Thank you for your interest in contributing to Markdown Table Fixer! This
document provides guidelines and instructions for contributing to the
project.

## Code of Conduct

This project follows The Linux Foundation's Code of Conduct. Please be
respectful and professional in all interactions.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- uv (recommended) or pip
- Git

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork locally:

   ```bash
   git clone https://github.com/YOUR_USERNAME/markdown-table-fixer.git
   cd markdown-table-fixer
   ```

3. Create a virtual environment and install dependencies:

   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e ".[dev]"
   ```

4. Install pre-commit hooks:

   ```bash
   pre-commit install
   ```

## Development Workflow

### Creating a Branch

Create a feature branch for your changes:

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:

- `feature/` - for new features
- `fix/` - for bug fixes
- `docs/` - for documentation changes
- `refactor/` - for code refactoring

### Making Changes

1. Write your code following the project's coding standards
2. Add or update tests as needed
3. Update documentation if you're changing functionality
4. Run the test suite to ensure nothing breaks

### Testing

Run tests with pytest:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=markdown_table_fixer --cov-report=html
```

### Code Quality

This project uses the following tools to maintain code quality:

- **ruff**: Code linting and formatting
- **mypy**: Static type checking
- **pre-commit**: Automated checks before commits

Run all checks:

```bash
pre-commit run --all-files
```

### Commit Messages

Follow these commit message conventions:

- Use the imperative mood ("Add feature" not "Added feature")
- Start with a capital letter
- Keep the first line under 72 characters
- Include a blank line between summary and description
- Reference issues and pull requests when relevant

Example:

```text
Add support for nested tables

This commit adds the ability to parse and fix tables nested within
other markdown structures like lists or blockquotes.

Fixes #123
```

All commits must include a sign-off:

```bash
git commit -s -m "Your commit message"
```

This adds a `Signed-off-by` line certifying that you have the right to
submit the code under the project's license.

## Pull Request Process

1. Update the README.md with details of changes if needed
2. Ensure all tests pass and code quality checks succeed
3. Update the documentation with any new features or changes
4. Submit a pull request to the `main` branch

### Pull Request Guidelines

- Include a clear description of what the PR does
- Reference any related issues
- Ensure CI checks pass
- Keep PRs focused on a single feature or fix
- Be responsive to feedback and requests for changes

## Coding Standards

### Python Style

- Follow PEP 8 guidelines
- Use type hints for function arguments and return values
- Line length limit: 80 characters
- Use double quotes for strings
- Sort imports alphabetically within groups

### Documentation

- Use docstrings for all public modules, classes, and functions
- Follow Google-style docstring format
- Include examples in docstrings when helpful
- Keep documentation up to date with code changes

Example docstring:

```python
def parse_table(content: str) -> MarkdownTable:
    """Parse a markdown table from content.

    Args:
        content: The markdown content containing a table

    Returns:
        A parsed MarkdownTable object

    Raises:
        TableParseError: If the content fails to parse as a table

    Example:
        >>> table = parse_table("| A | B |\n|---|---|\n| 1 | 2 |")
        >>> print(table.column_count)
        2
    """
    ...
```

## Test Coverage

- Write tests for all new features
- Maintain or improve code coverage
- Use descriptive test names
- Follow the Arrange-Act-Assert pattern
- Use fixtures for common test setup

## Reporting Issues

### Bug Reports

When reporting bugs, include:

- A clear description of the issue
- Steps to reproduce the problem
- Expected vs actual behavior
- Your environment (OS, Python version, etc.)
- Relevant code samples or markdown files
- Error messages or stack traces

### Feature Requests

When suggesting features, include:

- A clear description of the feature
- The problem it solves or use case it addresses
- Examples of how it would work
- Any alternative solutions you've considered

## License

By contributing to this project, you agree that your contributions
fall under the Apache License 2.0.

## Questions?

If you have questions about contributing, please open an issue on GitHub or
reach out to the maintainers.

Thank you for contributing to Markdown Table Fixer!
