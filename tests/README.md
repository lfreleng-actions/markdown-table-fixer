<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Test Suite Documentation

This directory contains the test suite for markdown-table-fixer. The tests
provide full isolation from the local development environment and run
in pre-commit hooks without side effects.

## Table of Contents

- [Running Tests](#running-tests)
- [Test Isolation](#test-isolation)
- [Test Organization](#test-organization)
- [Writing Tests](#writing-tests)
- [Pre-commit Integration](#pre-commit-integration)
- [Troubleshooting](#troubleshooting)

## Running Tests

### Basic Test Execution

Run all tests:

```bash
uv run pytest
```

Run tests without coverage (faster):

```bash
uv run pytest --no-cov
```

Run specific test file:

```bash
uv run pytest tests/test_git_config.py
```

Run tests with verbose output:

```bash
uv run pytest -v
```

Run tests and stop at first failure:

```bash
uv run pytest -x
```

### Test Markers

Tests use custom markers for selective execution:

Run unit tests (excluding integration tests):

```bash
uv run pytest -m "not integration"
```

Run git-related tests:

```bash
uv run pytest -m git
```

## Test Isolation

The test suite implements comprehensive isolation to ensure tests:

1. **Don't change the developer's git configuration**
2. **Don't affect the project repository**
3. **Don't make external network calls**
4. **Are reproducible across environments**

### Git Configuration Isolation

All tests run with isolated git configuration provided by the
`isolate_git_environment` fixture in `conftest.py`:

- `GIT_CONFIG_GLOBAL` points to a temporary file (not `~/.gitconfig`)
- `GIT_CONFIG_SYSTEM` points to a temporary file (not `/etc/gitconfig`)
- `HOME` points to a temporary directory
- `XDG_CONFIG_HOME` points to a temporary directory
- Git identity uses test-specific values

This means:

- Tests can't read your personal git config
- Tests can't change your personal git config
- Each test session uses fresh, isolated git configuration

### Repository Isolation

Tests that need to perform git operations use the `isolated_git_repo`
fixture, which:

- Creates a new temporary git repository for each test
- Configures the repository with test-specific identity
- Disables GPG signing
- Cleans up automatically after the test

Example:

```python
def test_git_operation(isolated_git_repo: Path) -> None:
    """Test that performs git operations in isolation."""
    # This is an isolated repository
    test_file = isolated_git_repo / "test.md"
    test_file.write_text("# Test")

    subprocess.run(["git", "add", "."], cwd=isolated_git_repo)
    subprocess.run(["git", "commit", "-m", "Test"], cwd=isolated_git_repo)
    # Repository cleans up automatically after test
```

### Network Isolation

By default, tests cannot make external network calls through the
`no_external_network` fixture. This:

- Patches `httpx.Client` and `httpx.AsyncClient`
- Patches `requests` methods
- Raises `RuntimeError` if network calls occur

Tests that need to make network calls should either:

1. **Mock the calls** (preferred):

```python
def test_api_call(mocker):
    """Test with mocked network call."""
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}

    mocker.patch("httpx.get", return_value=mock_response)
    # Test code that makes API calls
```

1. **Use the integration marker** (for actual network tests):

```python
@pytest.mark.integration
def test_real_api_call():
    """Test that makes real network calls."""
    response = httpx.get("https://api.github.com")
    assert response.status_code == 200
```

## Test Organization

Tests organize by functionality:

- `test_emoji_detection.py` - Emoji detection and Unicode width calculations
- `test_git_config.py` - Git configuration and identity management
- `test_jsonc_comments.py` - JSONC comment parsing
- `test_markdownlint_comments.py` - Markdownlint comment handling
- `test_md013_config.py` - MD013 (line length) configuration parsing
- `test_md060_config.py` - MD060 (code fence style) configuration parsing
- `test_pipe_splitting.py` - Table pipe character splitting logic
- `test_table_parser.py` - Markdown table parsing
- `test_table_validator.py` - Table validation logic
- `test_unicode_width.py` - Unicode character width calculations

## Writing Tests

### Test Structure

Follow this structure for new tests:

```python
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Description of what this test module covers."""

from pathlib import Path
import pytest

from markdown_table_fixer.module import function_to_test


class TestFeatureName:
    """Tests for specific feature."""

    def test_basic_case(self) -> None:
        """Test description in present tense."""
        # Arrange
        input_data = "test input"

        # Act
        result = function_to_test(input_data)

        # Assert
        assert result == "expected output"

    def test_edge_case(self) -> None:
        """Test edge case description."""
        # Test implementation
        pass
```

### Using Fixtures

#### Temporary Directories

Use `tmp_path` for temporary file operations:

```python
def test_file_operation(tmp_path: Path) -> None:
    """Test file operations."""
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test")
    assert test_file.exists()
```

#### Isolated Git Repository

Use `isolated_git_repo` for git operations:

```python
def test_git_feature(isolated_git_repo: Path) -> None:
    """Test git-related feature."""
    # All git operations use isolation
    subprocess.run(["git", "status"], cwd=isolated_git_repo)
```

#### Mock Git Config

Use `mock_git_config` to mock git configuration:

```python
def test_with_mock_config(mock_git_config: dict[str, str]) -> None:
    """Test with mocked git config."""
    mock_git_config["user.name"] = "Test User"
    # Git config queries will return mocked values
```

### Mocking

Use `pytest-mock` for mocking:

```python
def test_with_mock(mocker) -> None:
    """Test with mocked dependency."""
    mock_function = mocker.patch("module.function")
    mock_function.return_value = "mocked result"

    result = code_under_test()

    assert result == "expected"
    mock_function.assert_called_once()
```

### Async Tests

For async tests, use `pytest-asyncio`:

```python
@pytest.mark.asyncio
async def test_async_function() -> None:
    """Test async functionality."""
    result = await async_function()
    assert result is not None
```

## Pre-commit Integration

The test suite runs automatically in pre-commit hooks via:

```yaml
- repo: local
  hooks:
    - id: pytest
      name: pytest
      entry: uv
      args: [run, pytest, --tb=short, -q, -x, --no-cov]
      language: system
      pass_filenames: false
      always_run: true
```

### Why This Configuration?

- `uv run pytest`: Runs pytest in the uv-managed environment with the
  project installed
- `--tb=short`: Shows concise traceback on failures
- `-q`: Quiet mode (less verbose output)
- `-x`: Stop at first failure (faster feedback)
- `--no-cov`: Skip coverage reporting (faster execution)
- `pass_filenames: false`: Don't pass changed files (tests run on full suite)
- `always_run: true`: Always run tests even if no Python files changed

### Safety Features

The pre-commit hook is safe because:

1. **Git isolation**: Tests use temporary git config, not your personal config
2. **Repository isolation**: Tests create temporary repositories for git ops
3. **No side effects**: Tests don't change the project repository or working
   directory
4. **Network isolation**: Tests can't make external API calls by default
5. **Fast execution**: With `--no-cov` and `-x`, tests fail fast and run
   in minimal time

## Troubleshooting

### ModuleNotFoundError: No module named 'markdown_table_fixer'

**Cause**: The package isn't installed in the environment.

**Solution**:

```bash
uv sync --all-extras
```

### Tests fail with "Network call attempted during test"

**Cause**: Test is trying to make external network call without mocking.

**Solution**:

1. Mock the network call (preferred):

```python
def test_feature(mocker):
    mocker.patch("httpx.get", return_value=mock_response)
```

1. Or mark as integration test:

```python
@pytest.mark.integration
def test_feature():
    # Real network calls allowed
    pass
```

### Git config tests fail or change my config

**Cause**: Isolation fixtures aren't working properly.

**Solution**:

1. Ensure `conftest.py` is present in `tests/` directory
2. Check that `isolate_git_environment` fixture is session-scoped and
   auto-used
3. Verify tests use `tmp_path` or `isolated_git_repo` fixtures
4. Check that tests don't use bare `git config --global` commands

### Pre-commit hook fails but tests pass locally

**Cause**: Different environment or missing dependencies.

**Solution**:

```bash
# Update pre-commit hooks
pre-commit clean
pre-commit install

# Reinstall dependencies
uv sync --all-extras

# Run pre-commit manually
pre-commit run pytest --all-files
```

### Tests are slow

**Cause**: Coverage collection adds overhead.

**Solution**:

Run tests without coverage during development:

```bash
uv run pytest --no-cov
```

Full coverage is necessary for CI/CD and final validation.

## Coverage

To generate coverage reports:

```bash
# Run with coverage (default)
uv run pytest

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

Current coverage target: **15%** (required threshold)

## Continuous Integration

Tests run automatically in CI/CD pipelines with full coverage reporting.
The test suite must:

- Pass all tests
- Meet required coverage threshold (15%)
- Complete within reasonable time
- Not require external network access (except integration tests)
- Be reproducible across different environments

## Contributing

When adding new tests:

1. Follow existing test patterns and structure
2. Use appropriate fixtures for isolation
3. Mock external dependencies
4. Add docstrings explaining what you test
5. Use descriptive test names (present tense)
6. Group related tests in classes
7. Add markers for categorization (`@pytest.mark.git`, etc.)
8. Ensure tests are fast and focused

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-mock documentation](https://pytest-mock.readthedocs.io/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
