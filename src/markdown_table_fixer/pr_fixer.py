# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Fixer for markdown tables in pull requests."""

from __future__ import annotations

from contextlib import suppress
import logging
from pathlib import Path
import re
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .github_client import GitHubClient

from .git_config import GitConfigMode, configure_git_identity
from .models import GitHubFixResult, MarkdownTable, PRInfo
from .rule_disabler import filter_violations_by_disabled_rules
from .table_fixer import FileFixer
from .table_parser import MarkdownFileScanner, TableParser
from .table_validator import TableValidator


class PRFixer:
    """Fix markdown tables in pull requests."""

    def __init__(
        self,
        client: GitHubClient,
        git_config_mode: str = GitConfigMode.USER_INHERIT,
    ):
        """Initialize PR fixer.

        Args:
            client: GitHub API client
            git_config_mode: Git configuration mode (USER_INHERIT, USER_NO_SIGN, or BOT_IDENTITY)
        """
        self.client = client
        self.git_config_mode = git_config_mode
        self.logger = logging.getLogger("markdown_table_fixer.pr_fixer")
        self._cached_max_line_length: int | None = None

    def _sanitize_message(self, message: str) -> str:
        """Sanitize error messages to remove tokens.

        Args:
            message: The message to sanitize

        Returns:
            Message with tokens redacted
        """
        if not message:
            return message

        # Redact tokens from URLs (x-access-token:TOKEN@ pattern)
        sanitized = re.sub(
            r"x-access-token:[^@]+@", "x-access-token:***REDACTED***@", message
        )

        # Also redact any remaining token-like strings (common GitHub token formats)
        sanitized = re.sub(
            r"gh[ps]_[a-zA-Z0-9]{36,}", "***REDACTED***", sanitized
        )

        return sanitized

    async def _get_markdownlint_max_line_length(
        self, owner: str, repo: str, branch: str
    ) -> int:
        """Fetch markdownlint config from repository and extract MD013 line_length.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name

        Returns:
            Configured line length, or 80 if not found
        """
        config_files = [
            ".markdownlintrc",
            ".markdownlint.json",
            ".markdownlint.jsonc",
            ".markdownlint.yaml",
            ".markdownlint.yml",
        ]

        import json

        import yaml

        for config_file in config_files:
            try:
                # Fetch config file from repository using GitHubClient
                content = await self.client.get_file_content(
                    owner, repo, config_file, branch
                )

                # Parse based on file extension
                config = None
                if config_file.endswith((".yaml", ".yml")):
                    config = yaml.safe_load(content)
                    if config is None:
                        config = {}
                elif config_file.endswith((".json", ".jsonc", "rc")):
                    if config_file.endswith(".jsonc"):
                        # Remove comments from JSONC
                        import re

                        content = re.sub(
                            r"//.*$", "", content, flags=re.MULTILINE
                        )
                        content = re.sub(
                            r"/\*.*?\*/", "", content, flags=re.DOTALL
                        )
                    config = json.loads(content)

                # Check if MD013 has line_length configured
                if config and "MD013" in config:
                    md013_config = config["MD013"]
                    if (
                        isinstance(md013_config, dict)
                        and "line_length" in md013_config
                    ):
                        line_length = md013_config["line_length"]
                        if isinstance(line_length, int):
                            self.logger.debug(
                                f"Found markdownlint config in {config_file}: MD013 line_length={line_length}"
                            )
                            return line_length

            except Exception as e:
                self.logger.debug(f"Could not fetch {config_file}: {e}")
                continue

        # Default to 80 if no config found
        self.logger.debug(
            "No markdownlint config found, using default line_length=80"
        )
        return 80

    def _check_table_needs_fixes(
        self, table: MarkdownTable, max_line_length: int
    ) -> tuple[bool, bool]:
        """Check if a table needs fixes or MD013 comments.

        Args:
            table: The table to check
            max_line_length: Maximum line length before needing MD013 disable

        Returns:
            Tuple of (has_validation_issues, needs_md013)
        """
        # Check for validation violations (including MD013)
        validator = TableValidator(table, max_line_length=max_line_length)
        violations = validator.validate()

        # Filter out violations that are in sections with disabled rules
        violations = filter_violations_by_disabled_rules(
            violations, table.file_path
        )

        has_validation_issues = len(violations) > 0

        # Check if any line exceeds max_line_length (for MD013 comment insertion)
        table_lines = [row.raw_line for row in table.rows]
        max_len = (
            max(len(line.rstrip()) for line in table_lines)
            if table_lines
            else 0
        )
        needs_md013 = max_len > max_line_length

        return has_validation_issues, needs_md013

    def _process_file_tables(
        self,
        filename: str,
        content: str,
        max_line_length: int,
    ) -> tuple[bool, bool, str]:
        """Process tables in a file and apply fixes if needed.

        This is a shared method used by both git and API update methods.

        Args:
            filename: File path/name
            content: File content
            max_line_length: Maximum line length for MD013 checking

        Returns:
            Tuple of (has_changes, has_issues, fixed_content)
            - has_changes: Whether the content was modified
            - has_issues: Whether validation issues were found
            - fixed_content: The fixed content (may be same as input)
        """
        from pathlib import Path

        from .table_fixer import FileFixer
        from .table_parser import TableParser

        # Parse tables from content
        # Create temp file for parsing
        temp_path = Path(f"/tmp/{filename}")
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(content, encoding="utf-8")

        parser = TableParser(temp_path)
        tables = parser.parse_file()

        if not tables:
            temp_path.unlink()
            return False, False, content

        # Check if any tables have issues or need MD013 comments
        has_validation_issues = False
        needs_md013 = False

        for table in tables:
            table_has_validation, table_needs_md013 = (
                self._check_table_needs_fixes(table, max_line_length)
            )

            self.logger.debug(
                f"Table at line {table.start_line}: validation_issues={table_has_validation}, needs_md013={table_needs_md013}"
            )

            if table_has_validation:
                has_validation_issues = True

            if table_needs_md013:
                needs_md013 = True

        # Skip if no issues and no MD013 needed
        if not has_validation_issues and not needs_md013:
            self.logger.debug(f"No issues found in {filename}")
            temp_path.unlink()
            return False, False, content

        if needs_md013 and not has_validation_issues:
            self.logger.debug(
                f"Tables in {filename} need MD013 comments (line length > {max_line_length})"
            )

        self.logger.debug(f"Found issues in {filename}, applying fixes")

        # Use FileFixer which handles both table formatting and MD013 comments
        # Pass max_line_length explicitly since temp file can't find .markdownlintrc
        file_fixer = FileFixer(temp_path, max_line_length=max_line_length)
        file_fixer.fix_file(tables, dry_run=False)

        # Read back the fixed content
        fixed_content = temp_path.read_text(encoding="utf-8")

        # Clean up temp file
        temp_path.unlink()

        # Check if content actually changed
        has_changes = fixed_content != content

        return has_changes, has_validation_issues, fixed_content

    def _create_error_pr_info(self, pr_url: str) -> PRInfo:
        """Create a dummy PRInfo for error responses.

        Args:
            pr_url: PR URL for error messages

        Returns:
            PRInfo with dummy values for error cases
        """
        return PRInfo(
            number=0,
            title="",
            repository="",
            url=pr_url,
            author="",
            is_draft=False,
            head_ref="",
            head_sha="",
            base_ref="",
            mergeable="",
            merge_state_status="",
        )

    def _validate_parameters(
        self,
        pr_url: str,
        update_method: str,
        sync_strategy: str,
        conflict_strategy: str,
    ) -> GitHubFixResult | None:
        """Validate input parameters.

        Args:
            pr_url: PR URL for error messages
            update_method: Update method (already normalized)
            sync_strategy: Sync strategy (already normalized)
            conflict_strategy: Conflict strategy (already normalized)

        Returns:
            GitHubFixResult with error if validation fails, None if valid
        """
        # Validate update_method
        if update_method not in ["git", "api"]:
            return GitHubFixResult(
                pr_info=self._create_error_pr_info(pr_url),
                success=False,
                message=f"Invalid update_method '{update_method}'. Use 'git' or 'api'",
            )

        # Validate sync_strategy (only relevant for git method)
        if update_method == "git" and sync_strategy not in [
            "none",
            "rebase",
            "merge",
        ]:
            return GitHubFixResult(
                pr_info=self._create_error_pr_info(pr_url),
                success=False,
                message=f"Invalid sync_strategy '{sync_strategy}'. Use 'none', 'rebase', or 'merge'",
            )

        # Validate conflict_strategy (only relevant for git method)
        if update_method == "git" and conflict_strategy not in [
            "fail",
            "ours",
            "theirs",
        ]:
            return GitHubFixResult(
                pr_info=self._create_error_pr_info(pr_url),
                success=False,
                message=f"Invalid conflict_strategy '{conflict_strategy}'. Use 'fail', 'ours', or 'theirs'",
            )

        return None

    async def fix_pr_by_url(  # noqa: PLR0911
        self,
        pr_url: str,
        *,
        sync_strategy: str = "none",
        conflict_strategy: str = "fail",
        dry_run: bool = False,
        update_method: str = "api",
        pr_changes_only: bool = False,
        add_dco: bool = True,
    ) -> GitHubFixResult:
        """Fix markdown tables in a PR by URL.

        Args:
            pr_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/123)
            sync_strategy: How to sync with base branch: 'none', 'rebase', or 'merge' (git method only)
            conflict_strategy: How to resolve conflicts: 'fail', 'ours', or 'theirs' (git method only)
            dry_run: If True, don't actually push changes
            update_method: Method to apply fixes: 'git' (clone, amend, push) or 'api' (GitHub API)
            pr_changes_only: If True, only process files changed in the PR (default: False, process all markdown files)
            add_dco: If True, add DCO Signed-off-by trailer to commits (default: True)

        Returns:
            GitHubFixResult with operation details
        """
        # Normalize parameters to lowercase for case-insensitive comparison
        update_method = update_method.lower()
        sync_strategy = sync_strategy.lower()
        conflict_strategy = conflict_strategy.lower()

        # Validate parameters
        validation_error = self._validate_parameters(
            pr_url, update_method, sync_strategy, conflict_strategy
        )
        if validation_error:
            return validation_error

        # Parse PR URL
        match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url
        )
        if not match:
            return GitHubFixResult(
                pr_info=PRInfo(
                    number=0,
                    title="",
                    repository="",
                    url=pr_url,
                    author="",
                    is_draft=False,
                    head_ref="",
                    head_sha="",
                    base_ref="",
                    mergeable="",
                    merge_state_status="",
                ),
                success=False,
                message=f"Invalid PR URL format: {pr_url}",
            )

        owner, repo, pr_number_str = match.groups()
        pr_number = int(pr_number_str)

        self.logger.debug(f"Processing PR: {owner}/{repo}#{pr_number}")

        try:
            # Get PR details
            pr_data = await self.client._request(
                "GET", f"/repos/{owner}/{repo}/pulls/{pr_number}"
            )

            if not isinstance(pr_data, dict):
                return GitHubFixResult(
                    pr_info=PRInfo(
                        number=pr_number,
                        title="",
                        repository=f"{owner}/{repo}",
                        url=pr_url,
                        author="",
                        is_draft=False,
                        head_ref="",
                        head_sha="",
                        base_ref="",
                        mergeable="",
                        merge_state_status="",
                    ),
                    success=False,
                    message="Failed to fetch PR data",
                )

            head = pr_data.get("head", {})
            head_sha = head.get("sha", "")
            head_ref = head.get("ref", "")
            head_repo = head.get("repo", {})
            clone_url = head_repo.get("clone_url", "")

            pr_info = PRInfo(
                number=pr_number,
                title=pr_data.get("title", ""),
                repository=f"{owner}/{repo}",
                url=pr_url,
                author=pr_data.get("user", {}).get("login", ""),
                is_draft=pr_data.get("draft", False),
                head_ref=head_ref,
                head_sha=head_sha,
                base_ref=pr_data.get("base", {}).get("ref", ""),
                mergeable=pr_data.get("mergeable", "unknown"),
                merge_state_status=pr_data.get("mergeable_state", "unknown"),
            )

            # Check if PR is closed
            pr_state = pr_data.get("state", "").lower()
            if pr_state != "open":
                # Check if it was merged
                is_merged = pr_data.get("merged", False)
                state_display = (
                    "merged"
                    if is_merged
                    else (pr_state if pr_state else "closed")
                )
                return GitHubFixResult(
                    pr_info=pr_info,
                    success=False,
                    message=f"Pull request #{pr_number} is {state_display} and cannot be processed",
                )

            if not clone_url and update_method == "git":
                return GitHubFixResult(
                    pr_info=pr_info,
                    success=False,
                    message="PR head repository not accessible",
                )

            # Route to appropriate update method
            if update_method == "api":
                # Use GitHub API to update files
                return await self._fix_pr_with_api(
                    pr_info,
                    owner,
                    repo,
                    pr_data,
                    dry_run=dry_run,
                    pr_changes_only=pr_changes_only,
                    add_dco=add_dco,
                )
            else:
                # Clone and fix using Git operations
                return await self._fix_pr_with_git(
                    pr_info,
                    clone_url,
                    owner,
                    repo,
                    sync_strategy=sync_strategy,
                    conflict_strategy=conflict_strategy,
                    dry_run=dry_run,
                    pr_changes_only=pr_changes_only,
                )

        except Exception as e:
            self.logger.error(f"Error fixing PR: {e}", exc_info=True)
            return GitHubFixResult(
                pr_info=PRInfo(
                    number=pr_number,
                    title="",
                    repository=f"{owner}/{repo}",
                    url=pr_url,
                    author="",
                    is_draft=False,
                    head_ref="",
                    head_sha="",
                    base_ref="",
                    mergeable="",
                    merge_state_status="",
                ),
                success=False,
                message=str(e),
                error=str(e),
            )

    async def _fix_pr_with_git(
        self,
        pr_info: PRInfo,
        clone_url: str,
        owner: str,
        repo: str,
        *,
        sync_strategy: str = "none",
        conflict_strategy: str = "fail",
        dry_run: bool = False,
        git_config_mode: str | None = None,
        pr_changes_only: bool = False,
    ) -> GitHubFixResult:
        """Fix PR using Git operations (clone, fix, amend, push).

        Args:
            pr_info: PR information
            clone_url: Repository clone URL
            owner: Repository owner
            repo: Repository name
            sync_strategy: How to sync with base branch: 'none', 'rebase', or 'merge'
            conflict_strategy: How to resolve conflicts: 'fail', 'ours', or 'theirs'
            dry_run: If True, don't push changes
            git_config_mode: Override git config mode for this operation
            pr_changes_only: If True, only process files changed in the PR

        Returns:
            GitHubFixResult with operation details
        """
        # Use provided mode or fall back to instance default
        config_mode = git_config_mode or self.git_config_mode
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir) / "repo"
            self.logger.debug(f"Cloning {clone_url} to {repo_dir}")

            try:
                # Clone the repository with authentication
                # Note: Token is embedded in URL for git authentication. We use capture_output=True
                # and sanitize all error messages to prevent token leakage in logs.
                auth_url = clone_url.replace(
                    "https://", f"https://x-access-token:{self.client.token}@"
                )
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--branch",
                        pr_info.head_ref,
                        auth_url,
                        str(repo_dir),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                # Sync with base branch if requested
                if sync_strategy in ["rebase", "merge"]:
                    try:
                        await self._sync_with_base(
                            repo_dir,
                            pr_info.base_ref,
                            pr_info.head_ref,
                            sync_strategy,
                            conflict_strategy,
                        )
                    except subprocess.CalledProcessError as e:
                        sanitized_stderr = self._sanitize_message(
                            e.stderr or ""
                        )
                        sanitized_error = self._sanitize_message(str(e))
                        error_msg = f"Failed to sync with base branch using {sync_strategy}: {sanitized_stderr}"
                        self.logger.error(error_msg)
                        raise RuntimeError(error_msg) from e

                # Find and fix markdown files
                if pr_changes_only:
                    # Only process files changed in the PR
                    changed_files = await self.client.get_pr_files(
                        owner, repo, pr_info.number
                    )
                    markdown_files = [
                        repo_dir / f.get("filename", "")
                        for f in changed_files
                        if f.get("filename", "").endswith(".md")
                        and f.get("status") != "removed"
                        and (repo_dir / f.get("filename", "")).exists()
                    ]
                else:
                    # Scan all markdown files in the repository
                    scanner = MarkdownFileScanner(repo_dir)
                    markdown_files = scanner.find_markdown_files()

                self.logger.debug(f"Found {len(markdown_files)} markdown files")

                files_modified = []
                tables_fixed = 0
                tables_with_md013 = 0
                tables_with_md060 = 0

                for md_file in markdown_files:
                    self.logger.debug(f"Processing {md_file}")

                    # Parse tables
                    parser = TableParser(md_file)
                    tables = parser.parse_file()

                    if not tables:
                        continue

                    # Check if any tables have issues or need MD013 comments
                    # Auto-detect max line length from markdownlint config in the repo
                    if self._cached_max_line_length is None:
                        self._cached_max_line_length = (
                            await self._get_markdownlint_max_line_length(
                                owner, repo, pr_info.head_ref
                            )
                        )
                    max_line_length = self._cached_max_line_length

                    has_issues = False
                    needs_md013 = False

                    for table in tables:
                        has_validation_issues, table_needs_md013 = (
                            self._check_table_needs_fixes(
                                table, max_line_length
                            )
                        )

                        if has_validation_issues:
                            has_issues = True

                        if table_needs_md013:
                            needs_md013 = True

                    # Skip if no issues and no MD013 needed
                    if not has_issues and not needs_md013:
                        continue

                    # Fix the file (auto-detect line length from markdownlint config)
                    fixer = FileFixer(md_file)
                    fix_result = fixer.fix_file(tables, dry_run=False)

                    # Track results
                    files_modified.append(md_file)
                    tables_fixed += fix_result.tables_fixed
                    tables_with_md013 += fix_result.tables_with_md013
                    tables_with_md060 += fix_result.tables_with_md060

                    # Log what was done
                    if fix_result.tables_fixed > 0:
                        self.logger.debug(
                            f"Fixed {fix_result.tables_fixed} table(s) in {md_file.name}"
                        )
                    if fix_result.tables_with_md013 > 0:
                        self.logger.debug(
                            f"Added MD013 comments for {fix_result.tables_with_md013} table(s) in {md_file.name}"
                        )
                    if fix_result.tables_with_md060 > 0:
                        self.logger.debug(
                            f"Added MD060 comments for {fix_result.tables_with_md060} table(s) in {md_file.name}"
                        )

                # Handle no files modified or dry-run mode
                if not files_modified or dry_run:
                    if not files_modified:
                        message = "No markdown table issues found"
                        result_files: list[Path] = []
                    else:
                        file_names = [
                            str(f.relative_to(repo_dir)) for f in files_modified
                        ]
                        # Build multi-line message breaking down each type of fix
                        message_lines = [
                            f"Would fix {len(files_modified)} file(s): {', '.join(file_names)}"
                        ]

                        if tables_fixed > 0:
                            message_lines.append(
                                f"   {tables_fixed} table(s) with alignment/spacing issues"
                            )
                        if tables_with_md013 > 0:
                            message_lines.append(
                                f"   {tables_with_md013} table(s) with MD013 comments"
                            )
                        if tables_with_md060 > 0:
                            message_lines.append(
                                f"   {tables_with_md060} table(s) with MD060 comments"
                            )

                        message = "\n".join(message_lines)
                        result_files = files_modified
                    return GitHubFixResult(
                        pr_info=pr_info,
                        success=True,
                        message=message,
                        files_modified=result_files,
                    )

                # Configure git identity and signing
                git_config = configure_git_identity(
                    repo_dir,
                    mode=config_mode,
                    bot_name="markdown-table-fixer",
                    bot_email="noreply@linuxfoundation.org",
                )
                self.logger.debug(f"Git config applied: {git_config}")

                # Stage the changes
                for file_path in files_modified:
                    rel_path = file_path.relative_to(repo_dir)
                    subprocess.run(
                        ["git", "add", str(rel_path)],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                    )

                # Check if there are actually changes to commit
                result = subprocess.run(
                    ["git", "diff", "--cached", "--quiet"],
                    check=False,
                    cwd=repo_dir,
                    capture_output=True,
                )

                if result.returncode == 0:
                    # No changes - return early with success
                    self.logger.debug("No formatting changes needed")
                    return GitHubFixResult(
                        pr_info=pr_info,
                        success=True,
                        message="⏩ Files were already properly formatted",
                        files_modified=[],
                    )

                # Amend the last commit
                self.logger.debug("Amending last commit with table fixes")
                subprocess.run(
                    ["git", "commit", "--amend", "--no-edit"],
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )

                # Force push to update the PR
                # IMPORTANT: We use --force-with-lease instead of --force for safety in async environments:
                # - PR authors may push new commits while we're processing
                # - CI/CD systems may push commits concurrently
                # - Multiple tool instances could process the same PR simultaneously
                # --force-with-lease will FAIL if the remote branch has changed since our clone,
                # preventing us from accidentally overwriting commits. This is critical even though
                # we clone fresh, because the remote can change AFTER clone but BEFORE push.
                self.logger.debug(f"Force pushing to {pr_info.head_ref}")
                try:
                    subprocess.run(
                        [
                            "git",
                            "push",
                            "--force-with-lease",
                            "origin",
                            pr_info.head_ref,
                        ],
                        cwd=repo_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except subprocess.CalledProcessError as e:
                    # --force-with-lease failed, likely because remote branch was updated
                    sanitized_stderr = self._sanitize_message(e.stderr or "")
                    self.logger.warning(
                        f"Push rejected - remote branch {pr_info.head_ref} was updated during processing: {sanitized_stderr}"
                    )
                    error_msg = "Push rejected: PR branch was updated while processing. Please retry."
                    raise RuntimeError(error_msg) from e

                # Create a comment on the PR
                sync_msg = ""
                if sync_strategy == "rebase":
                    sync_msg = " and rebased onto the base branch"
                elif sync_strategy == "merge":
                    sync_msg = " and merged with the base branch"

                comment_body = (
                    f"🛠️ **Markdown Table Fixer**\n\n"
                    f"Fixed {tables_fixed} markdown table(s) in {len(files_modified)} file(s).\n\n"
                    f"The commit has been amended{sync_msg} with the formatting fixes.\n\n"
                    f"---\n"
                    f"*Automatically fixed by [markdown-table-fixer]"
                    f"(https://github.com/lfreleng-actions/markdown-table-fixer)*"
                )

                with suppress(Exception):
                    await self.client.create_comment(
                        owner, repo, pr_info.number, comment_body
                    )

                # Build multi-line message with file names and breakdown
                file_names = [
                    str(f.relative_to(repo_dir)) for f in files_modified
                ]
                message_lines = [
                    f"Fixed {len(files_modified)} file(s): {', '.join(file_names)}"
                ]

                if tables_fixed > 0:
                    message_lines.append(
                        f"   {tables_fixed} table(s) with alignment/spacing issues"
                    )
                if tables_with_md013 > 0:
                    message_lines.append(
                        f"   {tables_with_md013} table(s) with MD013 comments"
                    )
                if tables_with_md060 > 0:
                    message_lines.append(
                        f"   {tables_with_md060} table(s) with MD060 comments"
                    )

                return GitHubFixResult(
                    pr_info=pr_info,
                    success=True,
                    message="\n".join(message_lines),
                    files_modified=files_modified,
                )

            except subprocess.CalledProcessError as e:
                sanitized_stderr = self._sanitize_message(e.stderr or "")
                sanitized_error = self._sanitize_message(str(e))
                self.logger.error(f"Git operation failed: {sanitized_stderr}")
                return GitHubFixResult(
                    pr_info=pr_info,
                    success=False,
                    message=f"Git operation failed: {sanitized_stderr}",
                    error=sanitized_error,
                )
            except RuntimeError as e:
                # Handle expected errors (sync failures, push rejections)
                return GitHubFixResult(
                    pr_info=pr_info,
                    success=False,
                    message=str(e),
                    error=str(e),
                )
            except Exception as e:
                self.logger.error(f"Error during fix: {e}", exc_info=True)
                return GitHubFixResult(
                    pr_info=pr_info,
                    success=False,
                    message=str(e),
                    error=str(e),
                )

    async def _sync_with_base(
        self,
        repo_dir: Path,
        base_ref: str,
        head_ref: str,
        sync_strategy: str,
        conflict_strategy: str = "fail",
    ) -> None:
        """Sync PR branch with base branch using specified strategy.

        Args:
            repo_dir: Local repository directory
            base_ref: Base branch name (e.g., 'main')
            head_ref: PR branch name
            sync_strategy: 'rebase' or 'merge'
            conflict_strategy: How to resolve conflicts: 'fail', 'ours', or 'theirs'

        Raises:
            subprocess.CalledProcessError: If sync operation fails
        """
        # Fetch the base branch
        self.logger.debug(f"Fetching origin/{base_ref}")
        subprocess.run(
            ["git", "fetch", "origin", base_ref],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )

        if sync_strategy == "rebase":
            self.logger.debug(f"Rebasing {head_ref} onto origin/{base_ref}")
            try:
                rebase_cmd = ["git", "rebase", f"origin/{base_ref}"]
                if conflict_strategy == "ours":
                    rebase_cmd.extend(["-X", "ours"])
                elif conflict_strategy == "theirs":
                    rebase_cmd.extend(["-X", "theirs"])

                subprocess.run(
                    rebase_cmd,
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.logger.debug("Rebase successful")
            except subprocess.CalledProcessError as e:
                if conflict_strategy == "fail":
                    # Abort rebase on failure
                    subprocess.run(
                        ["git", "rebase", "--abort"],
                        check=False,
                        cwd=repo_dir,
                        capture_output=True,
                    )
                    sanitized_stderr = self._sanitize_message(e.stderr or "")
                    error_msg = f"Rebase failed: {sanitized_stderr}"
                    self.logger.error(error_msg)
                    raise subprocess.CalledProcessError(
                        e.returncode, e.cmd, e.output, e.stderr
                    ) from e
                else:
                    self.logger.warning(
                        f"Rebase had conflicts, attempting to resolve with strategy '{conflict_strategy}'"
                    )

        elif sync_strategy == "merge":
            self.logger.debug(f"Merging origin/{base_ref} into {head_ref}")
            try:
                merge_cmd = [
                    "git",
                    "merge",
                    f"origin/{base_ref}",
                    "-m",
                    f"Merge {base_ref} into {head_ref} for markdown table fixes",
                    "--no-edit",
                    "--allow-unrelated-histories",
                ]

                if conflict_strategy == "ours":
                    merge_cmd.extend(["-X", "ours"])
                elif conflict_strategy == "theirs":
                    merge_cmd.extend(["-X", "theirs"])

                subprocess.run(
                    merge_cmd,
                    cwd=repo_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.logger.debug("Merge successful")
            except subprocess.CalledProcessError as e:
                if conflict_strategy == "fail":
                    # Abort merge on failure
                    subprocess.run(
                        ["git", "merge", "--abort"],
                        check=False,
                        cwd=repo_dir,
                        capture_output=True,
                    )
                    sanitized_stderr = self._sanitize_message(e.stderr or "")
                    error_msg = f"Merge failed: {sanitized_stderr}"
                    self.logger.error(error_msg)
                    raise subprocess.CalledProcessError(
                        e.returncode, e.cmd, e.output, e.stderr
                    ) from e
                else:
                    self.logger.warning(
                        f"Merge had conflicts, attempting to resolve with strategy '{conflict_strategy}'"
                    )

    async def _fix_pr_with_api(
        self,
        pr_info: PRInfo,
        owner: str,
        repo: str,
        pr_data: dict[str, Any],
        *,
        dry_run: bool = False,
        pr_changes_only: bool = False,
        add_dco: bool = True,
    ) -> GitHubFixResult:
        """Fix PR using GitHub API (updates files).

        Args:
            pr_info: PR information
            owner: Repository owner
            repo: Repository name
            pr_data: Full PR data from API
            dry_run: If True, don't actually push changes
            pr_changes_only: If True, only process files changed in the PR
            add_dco: If True, add DCO Signed-off-by trailer (default: True)

        Returns:
            GitHubFixResult with operation details
        """
        result = await self.fix_pr_tables(
            owner,
            repo,
            pr_data,
            dry_run=dry_run,
            create_comment=True,
            pr_changes_only=pr_changes_only,
            add_dco=add_dco,
        )

        if result.get("success"):
            files_modified = [
                Path(f["filename"]) for f in result.get("fixed_files", [])
            ]
            # Build message with file names
            # Note: API method doesn't track MD013/MD060 separately, so simpler message
            file_names = [f["filename"] for f in result.get("fixed_files", [])]
            if file_names:
                message = f"Fixed {result.get('files_fixed', 0)} file(s): {', '.join(file_names)}\n   {result.get('tables_fixed', 0)} table(s) with alignment/spacing issues"
            else:
                message = f"Fixed {result.get('tables_fixed', 0)} table(s)"

            return GitHubFixResult(
                pr_info=pr_info,
                success=True,
                message=message,
                files_modified=files_modified,
            )
        else:
            return GitHubFixResult(
                pr_info=pr_info,
                success=False,
                message=result.get("error", "Failed to fix tables via API"),
                error=result.get("error"),
            )

    async def fix_pr_tables(
        self,
        owner: str,
        repo: str,
        pr: dict[str, Any],
        *,
        dry_run: bool = False,
        create_comment: bool = True,
        pr_changes_only: bool = False,
        add_dco: bool = True,
    ) -> dict[str, Any]:
        """Fix markdown tables in a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr: Pull request data
            dry_run: If True, don't actually push changes
            create_comment: If True, create a comment summarizing fixes
            pr_changes_only: If True, only process files changed in the PR
            add_dco: If True, add DCO Signed-off-by trailer (default: True)

        Returns:
            Dictionary with fix results
        """
        pr_number = pr.get("number")
        branch = pr.get("head", {}).get("ref")
        head_sha = pr.get("head", {}).get("sha")

        self.logger.debug(f"PR #{pr_number}: branch={branch}, sha={head_sha}")

        if not pr_number or not branch or not head_sha:
            self.logger.error("Invalid PR data: missing required fields")
            return {
                "success": False,
                "error": "Invalid PR data",
                "files_fixed": 0,
                "tables_fixed": 0,
            }

        # Get markdown files - either from PR changes only or all in repo
        if pr_changes_only:
            # Only process files changed in the PR
            self.logger.debug(f"Fetching changed files for PR #{pr_number}")
            files = await self.client.get_pr_files(owner, repo, pr_number)
            self.logger.debug(f"Found {len(files)} changed files in PR")
            markdown_files = [
                f
                for f in files
                if f.get("filename", "").endswith(".md")
                and f.get("status") != "removed"
            ]
        else:
            # Process all markdown files in the repository
            self.logger.debug("Fetching all markdown files from repository")
            try:
                # Get all files from the repository at the PR branch
                tree_response = await self.client._request(
                    "GET",
                    f"/repos/{owner}/{repo}/git/trees/{head_sha}",
                    params={"recursive": "1"},
                )
                tree = (
                    tree_response.get("tree", [])
                    if isinstance(tree_response, dict)
                    else []
                )

                # Filter for markdown files
                markdown_files = [
                    {
                        "filename": item.get("path", ""),
                        "sha": item.get("sha", ""),
                    }
                    for item in tree
                    if item.get("type") == "blob"
                    and item.get("path", "").endswith(".md")
                ]
                self.logger.debug(
                    f"Found {len(markdown_files)} markdown files in repository"
                )
            except Exception as e:
                self.logger.error(f"Failed to fetch repository tree: {e}")
                return {
                    "success": False,
                    "error": f"Failed to fetch repository files: {e}",
                    "files_fixed": 0,
                    "tables_fixed": 0,
                }

        self.logger.debug(
            f"Found {len(markdown_files)} markdown files to process"
        )
        for f in markdown_files:
            self.logger.debug(f"  - {f.get('filename')}")

        if not markdown_files:
            self.logger.debug("No markdown files to fix")
            return {
                "success": True,
                "message": "No markdown files to fix",
                "files_fixed": 0,
                "tables_fixed": 0,
            }

        files_fixed = 0
        tables_fixed = 0
        fixed_files_list = []
        batch_updates = []  # Collect all file updates for single commit

        # First pass: analyze all files and collect changes
        for file_data in markdown_files:
            filename = file_data.get("filename", "")
            file_sha = file_data.get("sha")

            self.logger.debug(f"Processing file: {filename}")

            if not filename or not file_sha:
                self.logger.warning("Skipping file with missing name or SHA")
                continue

            try:
                # Get current file content
                self.logger.debug(f"Fetching content for {filename}")
                content = await self.client.get_file_content(
                    owner, repo, filename, branch
                )
                self.logger.debug(f"Content length: {len(content)} bytes")

                # Parse and fix tables by splitting content into lines
                lines = content.splitlines(keepends=True)
                self.logger.debug(f"File has {len(lines)} lines")

                # Create temp file to allow validation and filtering
                temp_path = Path(f"/tmp/{filename}")
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_text(content, encoding="utf-8")

                parser = TableParser(temp_path)
                tables = parser.parse_file()

                self.logger.debug(f"Found {len(tables)} tables in {filename}")

                if not tables:
                    self.logger.debug(f"No tables found in {filename}")
                    continue

                # Check if any tables have issues or need MD013 comments
                # Fetch max line length from repository's markdownlint config
                if self._cached_max_line_length is None:
                    self._cached_max_line_length = (
                        await self._get_markdownlint_max_line_length(
                            owner, repo, branch
                        )
                    )
                max_line_length = self._cached_max_line_length

                has_issues = False
                needs_md013 = False
                fixes_applied = 0

                for table in tables:
                    has_validation_issues, table_needs_md013 = (
                        self._check_table_needs_fixes(table, max_line_length)
                    )

                    self.logger.debug(
                        f"Table at line {table.start_line}: validation_issues={has_validation_issues}, needs_md013={table_needs_md013}"
                    )

                    if has_validation_issues:
                        has_issues = True
                        fixes_applied += 1

                    if table_needs_md013:
                        needs_md013 = True

                # Skip if no issues and no MD013 needed
                if not has_issues and not needs_md013:
                    self.logger.debug(f"No issues found in {filename}")
                    continue

                if needs_md013 and not has_issues:
                    self.logger.debug(
                        f"Tables in {filename} need MD013 comments (line length > {max_line_length})"
                    )

                self.logger.debug(f"Found issues in {filename}, applying fixes")

                # Use FileFixer which handles both table formatting and MD013 comments
                from .table_fixer import FileFixer

                # Temp file already created above during parsing
                # Pass max_line_length explicitly since temp file can't find .markdownlintrc
                file_fixer = FileFixer(
                    temp_path, max_line_length=max_line_length
                )
                file_fixer.fix_file(tables, dry_run=False)

                # Read back the fixed content
                fixed_content = temp_path.read_text(encoding="utf-8")

                # Clean up temp file
                temp_path.unlink()

                # Only collect if content changed
                if fixed_content != content:
                    self.logger.debug(f"Content changed for {filename}")
                    batch_updates.append(
                        {
                            "path": filename,
                            "content": fixed_content,
                        }
                    )
                    files_fixed += 1
                    tables_fixed += fixes_applied
                    fixed_files_list.append(
                        {"filename": filename, "tables": fixes_applied}
                    )
                else:
                    self.logger.debug(f"No content changes for {filename}")

            except Exception:
                # Continue with other files if one fails
                continue

        # Second pass: apply all updates in a single batch commit
        if batch_updates and not dry_run:
            self.logger.debug(
                f"Applying batch update: {len(batch_updates)} file(s) in single commit"
            )
            try:
                commit_message = (
                    f"Fix markdown table formatting\n\n"
                    f"Automatically fixed {tables_fixed} table(s) across "
                    f"{files_fixed} file(s) in PR #{pr_number}\n\n"
                    f"Files updated:\n"
                )
                for file_info in fixed_files_list:
                    filename = file_info["filename"]
                    table_count = file_info["tables"]
                    commit_message += f"- {filename}: {table_count} table(s)\n"

                # Set up author identity for commit
                author_name = "markdown-table-fixer"
                author_email = "markdown-table-fixer@linuxfoundation.org"

                # Add DCO sign-off if requested
                if add_dco:
                    commit_message += (
                        f"\nSigned-off-by: {author_name} <{author_email}>\n"
                    )

                await self.client.batch_update_files(
                    owner,
                    repo,
                    branch,
                    batch_updates,
                    commit_message,
                    author_name=author_name,
                    author_email=author_email,
                )
                self.logger.debug("Successfully applied batch update")
            except Exception as e:
                self.logger.error(f"Failed to apply batch update: {e}")
                return {
                    "success": False,
                    "error": f"Failed to apply batch update: {e}",
                    "files_fixed": 0,
                    "tables_fixed": 0,
                }

        self.logger.debug(
            f"PR fix complete: {files_fixed} files, {tables_fixed} tables"
        )

        # Create a comment if requested and fixes were made
        if create_comment and files_fixed > 0 and not dry_run:
            self.logger.debug("Creating PR comment")
            comment_body = self._generate_comment(
                files_fixed, tables_fixed, fixed_files_list
            )
            # Don't fail if comment creation fails
            with suppress(Exception):
                await self.client.create_comment(
                    owner, repo, pr_number, comment_body
                )

        return {
            "success": True,
            "files_fixed": files_fixed,
            "tables_fixed": tables_fixed,
            "fixed_files": fixed_files_list,
            "dry_run": dry_run,
        }

    def _generate_comment(
        self,
        files_fixed: int,
        tables_fixed: int,
        fixed_files: list[dict[str, Any]],
    ) -> str:
        """Generate a comment body for the PR.

        Args:
            files_fixed: Number of files fixed
            tables_fixed: Number of tables fixed
            fixed_files: List of fixed files with details

        Returns:
            Comment body text
        """
        lines = [
            "## 🛠️ Markdown Table Fixer",
            "",
            "Automatically fixed markdown table formatting issues:",
            f"- **{files_fixed}** file(s) updated",
            f"- **{tables_fixed}** table(s) fixed",
            "",
        ]

        if fixed_files:
            lines.append("### Files Updated:")
            for file_info in fixed_files:
                filename = file_info["filename"]
                table_count = file_info["tables"]
                lines.append(f"- `{filename}` - {table_count} table(s) fixed")
            lines.append("")

        lines.extend(
            [
                "---",
                "*This fix was automatically applied by "
                "[markdown-table-fixer](https://github.com/lfreleng-actions/markdown-table-fixer)*",
            ]
        )

        return "\n".join(lines)
