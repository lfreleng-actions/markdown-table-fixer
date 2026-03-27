# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Command-line interface for markdown-table-fixer."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from dependamerge import get_default_workers
from rich.console import Console
from rich.logging import RichHandler
import typer

from ._version import __version__
from .blocked_pr_scanner import BlockedPRScanner
from .exceptions import (
    FileAccessError,
    TableParseError,
)
from .git_config import GitConfigMode
from .github_client import GitHubClient
from .models import (
    BlockedPR,
    FileResult,
    OutputFormat,
    PRInfo,
    ScanResult,
)
from .pr_fixer import PRFixer
from .pr_scanner import PRScanner
from .progress_tracker import ProgressTracker
from .rule_disabler import filter_violations_by_disabled_rules
from .table_fixer import FileFixer
from .table_parser import MarkdownFileScanner, TableParser
from .table_validator import TableValidator

console = Console()


def get_version_string() -> str:
    """Get the formatted version string."""
    return f"🏷️  markdown-table-fixer version {__version__}"


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(get_version_string())
        console.print()
        raise typer.Exit()


def setup_logging(
    log_level: str = "INFO", quiet: bool = False, verbose: bool = False
) -> None:
    """Configure logging with Rich handler."""
    if quiet:
        log_level = "ERROR"
    elif verbose:
        log_level = "DEBUG"

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=[
            RichHandler(console=console, show_time=False, show_path=False)
        ],
    )

    # Silence httpx INFO logs to prevent Rich display interruption
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Create Typer app with custom help formatter
class CustomTyper(typer.Typer):  # type: ignore[misc]
    """Custom Typer class to add version to help output."""

    def __call__(self, *args: object, **kwargs: object) -> object:
        """Override to inject version string in help output."""
        # Check if help is being requested (for any command or subcommand)
        import sys

        if "--help" in sys.argv or "-h" in sys.argv:
            console.print(get_version_string())
        return super().__call__(*args, **kwargs)


# Create Typer app
app = CustomTyper(
    name="markdown-table-fixer",
    help="Fix markdown table formatting issues",
    add_completion=False,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    """Markdown table formatter and linter with GitHub integration."""
    pass


@app.command(help="Scan and optionally fix markdown table formatting issues")
def lint(
    path: Path = typer.Argument(
        Path("."),
        help="Path to scan for markdown files",
        exists=True,
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.TEXT,
        "--format",
        help="Output format: text, json",
        case_sensitive=False,
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress output except errors",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output with DEBUG logging",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Exit with error if issues found (CI mode)",
    ),
    max_line_length: int | None = typer.Option(
        None,
        "--max-line-length",
        help="Maximum line length before adding MD013 disable comments (default: auto-detect from .markdownlintrc)",
    ),
    auto_fix: bool = typer.Option(
        False,
        "--auto-fix/--no-auto-fix",
        help="Automatically fix issues found (default: disabled)",
    ),
    fail_on_error: bool = typer.Option(
        True,
        "--fail-on-error/--no-fail-on-error",
        help="Exit with error if issues found (default: enabled)",
    ),
) -> None:
    """Scan and optionally fix markdown table formatting issues.

    By default, scans the current directory and reports issues without fixing.
    Use --auto-fix to automatically fix issues found.

    Examples:
      markdown-table-fixer lint                    # Scan current directory
      markdown-table-fixer lint --auto-fix         # Scan and fix issues
      markdown-table-fixer lint /path/to/docs      # Scan specific path
      markdown-table-fixer lint --check            # CI mode: fail if issues found
      markdown-table-fixer lint --verbose          # Enable DEBUG logging
    """
    # Setup logging based on flags
    setup_logging(quiet=quiet, verbose=verbose)
    logger = logging.getLogger("markdown_table_fixer")

    # Use the positional path argument
    scan_path = path

    logger.debug(f"Starting lint scan of: {scan_path}")

    # Auto-detect max_line_length if not specified
    if max_line_length is None:
        max_line_length = _detect_max_line_length(scan_path)
        logger.debug(f"Auto-detected max_line_length: {max_line_length}")

    logger.debug(
        f"Options: auto_fix={auto_fix}, max_line_length={max_line_length}"
    )

    # Use auto_fix flag to determine if we should fix issues
    should_fix = auto_fix

    # Don't print status messages in JSON mode or when quiet
    if not quiet and output_format != OutputFormat.JSON:
        console.print(f"🔍 Scanning: {scan_path}")
        if should_fix:
            console.print("🔧 Auto-fix enabled")

    try:
        scanner = MarkdownFileScanner(scan_path)
        markdown_files = scanner.find_markdown_files()

        logger.debug(f"Found {len(markdown_files)} markdown files to scan")

        if not markdown_files:
            if not quiet:
                console.print(
                    f"[yellow]No markdown files found in {scan_path}[/yellow]"
                )
            return

        # Process files
        results = []
        for md_file in markdown_files:
            logger.debug(f"Processing file: {md_file}")
            result = _process_file(md_file, should_fix, max_line_length)
            results.append(result)
            logger.debug(
                f"Result: {len(result.violations)} violations, {len(result.fixes_applied)} fixes applied"
            )

        # Create scan result
        scan_result = ScanResult()
        for result in results:
            scan_result.add_file_result(result)

        # Output results
        if output_format == OutputFormat.JSON:
            _output_json_results(scan_result)
        else:
            _output_text_results(scan_result, quiet)

        # Exit with error if issues found and check mode
        if (check or fail_on_error) and scan_result.files_with_issues > 0:
            raise typer.Exit(1)

    except typer.Exit:
        # Re-raise typer.Exit without catching it as a general exception
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command(help="Fix markdown tables in GitHub pull requests")
def github(
    target: str = typer.Argument(
        ...,
        help="GitHub organization name/URL or PR URL (e.g., https://github.com/org or https://github.com/owner/repo/pull/123)",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="GitHub token (or set GITHUB_TOKEN env var)",
        envvar="GITHUB_TOKEN",
    ),
    sync_strategy: str = typer.Option(
        "none",
        "--sync-strategy",
        help="How to sync PR with base branch: 'rebase', 'merge', or 'none' (default: none)",
        case_sensitive=False,
    ),
    conflict_strategy: str = typer.Option(
        "fail",
        "--conflict-strategy",
        help="How to resolve conflicts: 'fail', 'ours' (keep PR changes), or 'theirs' (keep base changes)",
        case_sensitive=False,
    ),
    update_method: str = typer.Option(
        "git",
        "--update-method",
        help="Method to apply fixes: 'git' (clone, amend, push) or 'api' (GitHub API)",
        case_sensitive=False,
    ),
    disable_signing: bool = typer.Option(
        False,
        "--disable-signing",
        help="Disables commit signing (only applies to 'git' method)",
    ),
    bot_identity: bool = typer.Option(
        False,
        "--bot-identity",
        help="Use bot identity instead of user (only applies to 'git' method, disables commit signing)",
    ),
    pr_changes_only: bool = typer.Option(
        False,
        "--pr-changes-only",
        help="Only fix/process files updated in the pull request",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without applying them",
    ),
    no_dco: bool = typer.Option(
        False,
        "--no-dco",
        help="Disable adding DCO Signed-off-by trailer to commits (default: DCO is added)",
    ),
    include_drafts: bool = typer.Option(
        False,
        "--include-drafts",
        help="Include draft PRs in scan",
    ),
    no_blocked_only: bool = typer.Option(
        False,
        "--no-blocked-only",
        help="Process ALL PRs, not just blocked/unmergeable ones (default: only process blocked PRs)",
    ),
    debug_org: bool = typer.Option(
        False,
        "--debug-org",
        help="Debug mode: only process first PR found (useful for testing org scans)",
    ),
    _workers: int | None = typer.Option(
        None,
        "--workers",
        "-j",
        min=1,
        max=32,
        help="Number of parallel workers (auto-detects CPU cores if not specified)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress all output except errors",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Set logging level",
    ),
) -> None:
    """Fix markdown tables in GitHub PRs.

    Can process either:
    - An entire organization (scans all PRs for table issues)
    - A specific PR by URL

    Update Methods:
    - 'git' (default): Clone repo, amend commit, force-push (respects signing)
    - 'api': Use GitHub API to update files (shows as verified by GitHub)

    Git Identity & Signing (only applies to 'git' update method):
    - By default, uses your git user.name, user.email, and commit signing settings
    - --disable-signing: Use your identity but disable commit signing
    - --bot-identity: Use bot identity instead of user (disables commit signing)

    Sync strategies (only applies to 'git' update method):
    - 'none': Fix tables on PR branch as-is (may have conflicts)
    - 'rebase': Rebase PR onto base branch before fixing (cleaner history)
    - 'merge': Merge base branch into PR before fixing (safer)

    Conflict resolution strategies (when sync causes conflicts):
    - 'fail': Abort if conflicts occur (default, safest)
    - 'ours': Keep PR changes, discard conflicting base changes
    - 'theirs': Keep base changes, discard conflicting PR changes

    Examples:
      markdown-table-fixer github myorg --token ghp_xxx
      markdown-table-fixer github https://github.com/owner/repo/pull/123
      markdown-table-fixer github https://github.com/owner/repo/pull/123 --sync-strategy rebase
      markdown-table-fixer github https://github.com/owner/repo/pull/123 --sync-strategy merge --conflict-strategy ours
    """
    setup_logging(log_level=log_level, quiet=quiet, verbose=verbose)

    # Normalize and validate update method
    update_method = update_method.lower()
    if update_method not in ["git", "api"]:
        console.print(
            f"[red]Error:[/red] Invalid update method '{update_method}'. "
            "Use 'git' or 'api'"
        )
        raise typer.Exit(1)

    # Determine git config mode from CLI flags (only relevant for git method)
    if bot_identity and disable_signing:
        console.print(
            "[red]Error:[/red] Cannot use both --bot-identity and --disable-signing"
        )
        raise typer.Exit(1)

    if bot_identity:
        git_config_mode = GitConfigMode.BOT_IDENTITY
    elif disable_signing:
        git_config_mode = GitConfigMode.USER_NO_SIGN
    else:
        git_config_mode = GitConfigMode.USER_INHERIT

    # Normalize and validate sync strategy
    sync_strategy = sync_strategy.lower()
    if sync_strategy not in ["none", "rebase", "merge"]:
        console.print(
            f"[red]Error:[/red] Invalid sync strategy '{sync_strategy}'. "
            "Use 'none', 'rebase', or 'merge'"
        )
        raise typer.Exit(1)

    # Normalize and validate conflict strategy
    conflict_strategy = conflict_strategy.lower()
    if conflict_strategy not in ["fail", "ours", "theirs"]:
        console.print(
            f"[red]Error:[/red] Invalid conflict strategy '{conflict_strategy}'. "
            "Use 'fail', 'ours', or 'theirs'"
        )
        raise typer.Exit(1)

    if not token:
        console.print(
            "[red]Error:[/red] GitHub token required. "
            "Provide --token or set GITHUB_TOKEN environment variable"
        )
        raise typer.Exit(1)

    # Check if target is a PR URL or organization name
    if "/pull/" in target or "/pulls/" in target:
        # Single PR
        asyncio.run(
            _fix_single_pr(
                target,
                token,
                sync_strategy=sync_strategy,
                conflict_strategy=conflict_strategy,
                dry_run=dry_run,
                quiet=quiet,
                git_config_mode=git_config_mode,
                update_method=update_method,
                pr_changes_only=pr_changes_only,
                add_dco=not no_dco,
            )
        )
    else:
        # Scan organization
        asyncio.run(
            _scan_organization(
                target,
                token,
                sync_strategy=sync_strategy,
                conflict_strategy=conflict_strategy,
                dry_run=dry_run,
                include_drafts=include_drafts,
                blocked_only=not no_blocked_only,
                debug_org=debug_org,
                quiet=quiet,
                git_config_mode=git_config_mode,
                update_method=update_method,
                pr_changes_only=pr_changes_only,
                add_dco=not no_dco,
                workers=_workers
                if _workers is not None
                else get_default_workers(),
            )
        )


async def _fix_single_pr(
    pr_url: str,
    token: str,
    sync_strategy: str = "none",
    conflict_strategy: str = "fail",
    dry_run: bool = False,
    quiet: bool = False,
    git_config_mode: str = GitConfigMode.USER_INHERIT,
    update_method: str = "api",
    pr_changes_only: bool = False,
    add_dco: bool = True,
) -> None:
    """Fix markdown tables in a single PR."""
    logger = logging.getLogger("markdown_table_fixer.cli")

    if not quiet:
        console.print(f"🔍 Processing PR: {pr_url}")

        # Show update method info
        method_desc = (
            "Git clone/amend/push"
            if update_method.lower() == "git"
            else "GitHub API"
        )
        console.print(f"Update method: {method_desc}")

        # Show git identity info if using git method
        if update_method.lower() == "git":
            if git_config_mode == GitConfigMode.BOT_IDENTITY:
                console.print("Git identity: Bot (markdown-table-fixer)")
            elif git_config_mode == GitConfigMode.USER_NO_SIGN:
                console.print("Git identity: User (signing disabled)")
            else:
                console.print("Git identity: User (inheriting signing config)")

    try:
        async with GitHubClient(token) as client:  # type: ignore[attr-defined]
            fixer = PRFixer(client, git_config_mode=git_config_mode)
            result = await fixer.fix_pr_by_url(  # type: ignore[attr-defined]
                pr_url,
                sync_strategy=sync_strategy,
                conflict_strategy=conflict_strategy,
                dry_run=dry_run,
                update_method=update_method,
                pr_changes_only=pr_changes_only,
                add_dco=add_dco,
            )
            if result.success:
                if not quiet:
                    # Use different emoji for dry-run vs actual fixes
                    emoji = "☑️ " if dry_run else "✅"
                    # Handle multi-line messages - only first line gets emoji
                    message_lines = result.message.split("\n")
                    if message_lines:
                        console.print(
                            f"[green]{emoji} {message_lines[0]}[/green]"
                        )
                        # Print remaining lines without emoji, with indentation
                        for line in message_lines[1:]:
                            console.print(f"[green]{line}[/green]")
                    # Log temp file paths at debug level only (not shown to console)
                    if result.files_modified:
                        logger.debug("Modified files (temp paths):")
                        for file in result.files_modified:
                            logger.debug(f"  - {file}")
            elif not quiet:
                console.print(f"[yellow]⚠️  {result.message}[/yellow]")
                if result.error:
                    console.print(f"   Error: {result.error}")

    except Exception as e:
        console.print(f"[red]Error processing PR:[/red] {e}")
        raise typer.Exit(1) from e


async def _scan_organization(
    org: str,
    token: str,
    sync_strategy: str = "none",
    conflict_strategy: str = "fail",
    dry_run: bool = False,
    include_drafts: bool = False,
    blocked_only: bool = True,
    debug_org: bool = False,
    quiet: bool = False,
    git_config_mode: str = GitConfigMode.USER_INHERIT,
    update_method: str = "api",
    pr_changes_only: bool = False,
    add_dco: bool = True,
    workers: int = 8,
) -> None:
    """Scan organization for PRs with markdown table issues."""
    # Remove github.com prefix if present
    if "github.com" in org:
        org = org.split("github.com/")[-1].strip("/")

    if not quiet:
        console.print(f"🔍 Scanning organization: {org}")

    try:
        async with GitHubClient(token) as client:  # type: ignore[attr-defined]
            # Create progress tracker for visual feedback
            progress_tracker = (
                None if quiet else ProgressTracker(org, show_pr_stats=True)
            )

            fixer = PRFixer(client, git_config_mode=git_config_mode)

            # Inform about update method
            if not quiet:
                method_desc = (
                    "Git clone/amend/push"
                    if update_method.lower() == "git"
                    else "GitHub API"
                )
                console.print(f"Update method: {method_desc}")
                if update_method.lower() == "git":
                    if git_config_mode == GitConfigMode.BOT_IDENTITY:
                        console.print(
                            "Git identity: Bot (markdown-table-fixer)"
                        )
                    elif git_config_mode == GitConfigMode.USER_NO_SIGN:
                        console.print("Git identity: User (signing disabled)")
                    else:
                        console.print(
                            "Git identity: User (inheriting signing config)"
                        )

                # Show filtering status
                if not blocked_only:
                    console.print(
                        "⚠️  Processing ALL PRs (not just blocked ones)"
                    )
                else:
                    console.print("🚫 Only processing blocked/unmergeable PRs")
                console.print()

            # Collect PRs from async generator
            prs_to_process = []

            # Use BlockedPRScanner (dependamerge) when filtering to blocked PRs only
            # This ensures consistent blocking logic with other tools
            if blocked_only:
                # Use dependamerge's GitHubService for blocked PR detection
                blocked_scanner = BlockedPRScanner(
                    token=token,
                    progress_tracker=progress_tracker,
                    max_repo_tasks=workers,
                )

                # Note: progress_tracker.start() is called by scanner internally
                try:
                    async for (
                        owner,
                        repo_name,
                        _pr_data,
                        unmergeable_pr,
                    ) in blocked_scanner.scan_organization_for_blocked_prs(
                        org, include_drafts=include_drafts
                    ):
                        pr_info = PRInfo(
                            number=unmergeable_pr.pr_number,
                            title=unmergeable_pr.title,
                            repository=f"{owner}/{repo_name}",
                            url=unmergeable_pr.url,
                            author=unmergeable_pr.author,
                            is_draft=False,  # Drafts are filtered by dependamerge
                            head_ref="",  # Not provided by dependamerge
                            head_sha="",  # Not provided by dependamerge
                            base_ref="",  # Not provided by dependamerge
                            mergeable="",  # Will be determined by blocking reasons
                            merge_state_status="",  # Will be determined by blocking reasons
                        )

                        # Extract blocking reasons from dependamerge
                        blocking_reasons = [
                            r.description for r in unmergeable_pr.reasons
                        ]

                        blocked_pr = BlockedPR(
                            pr_info=pr_info,
                            blocking_reasons=blocking_reasons,
                            has_markdown_issues=True,  # Will be verified when we try to fix
                        )

                        prs_to_process.append(blocked_pr)
                finally:
                    await blocked_scanner.close()
            else:
                # Use original PRScanner for all PRs (no blocking filter)
                scanner = PRScanner(client, progress_tracker=progress_tracker)

                if progress_tracker:
                    progress_tracker.start()

                # Scanner yields PRs (it counts repos internally using GraphQL)
                try:
                    async for (
                        owner,
                        repo_name,
                        pr_data,
                    ) in scanner.scan_organization(
                        org, include_drafts=include_drafts
                    ):
                        pr_info = PRInfo(
                            number=pr_data.get("number", 0),
                            title=pr_data.get("title", ""),
                            repository=f"{owner}/{repo_name}",
                            url=pr_data.get("html_url", ""),
                            author=pr_data.get("user", {}).get("login", ""),
                            is_draft=pr_data.get("draft", False),
                            head_ref=pr_data.get("head", {}).get("ref", ""),
                            head_sha=pr_data.get("head", {}).get("sha", ""),
                            base_ref=pr_data.get("base", {}).get("ref", ""),
                            mergeable=pr_data.get("mergeable_state", ""),
                            merge_state_status=pr_data.get(
                                "merge_state_status", ""
                            ),
                        )

                        blocked_pr = BlockedPR(
                            pr_info=pr_info,
                            blocking_reasons=["Needs markdown table fixes"],
                            has_markdown_issues=True,  # Will be verified when we try to fix
                        )

                        prs_to_process.append(blocked_pr)
                except Exception as scan_error:
                    # Stop progress tracker on error
                    if progress_tracker:
                        progress_tracker.stop()
                    console.print(
                        f"\n[yellow]⚠️  Scanning interrupted: {scan_error}[/yellow]"
                    )
                    console.print(
                        "[yellow]Processing PRs found so far...[/yellow]"
                    )

                # Stop progress tracker
                if progress_tracker:
                    progress_tracker.stop()

            if not prs_to_process:
                if blocked_only:
                    console.print(
                        "\n[green]✅ No blocked PRs with markdown table issues found![/green]"
                    )
                else:
                    console.print(
                        "\n[green]✅ No PRs with markdown table issues found![/green]"
                    )
                return

            # Display PRs
            if not quiet:
                console.print(
                    "\n🔍 Examining blocked pull requests for markdown/linting failures"
                )
                for blocked_pr in prs_to_process:
                    console.print(
                        f"   • {blocked_pr.pr_info.repository}#{blocked_pr.pr_info.number}: {blocked_pr.pr_info.title}"
                    )

            # Debug mode: limit to first PR only
            if debug_org and prs_to_process:
                if not quiet:
                    console.print(
                        "\n[yellow]🐛 GitHub Organisation DEBUG mode: only processing first pull request[/yellow]"
                    )
                prs_to_process = prs_to_process[:1]

            prs_fixed = 0
            prs_with_issues = 0
            fixed_pr_urls = []

            # Process PRs sequentially to avoid overwhelming the system
            for blocked_pr in prs_to_process:
                try:
                    if not quiet:
                        console.print(f"\n🔄 {blocked_pr.pr_info.url}")

                    result = await fixer.fix_pr_by_url(
                        blocked_pr.pr_info.url,
                        sync_strategy=sync_strategy,
                        conflict_strategy=conflict_strategy,
                        dry_run=dry_run,
                        update_method=update_method,
                        pr_changes_only=pr_changes_only,
                        add_dco=add_dco,
                    )

                    if result.success:
                        if len(result.files_modified) > 0:
                            prs_fixed += 1
                            fixed_pr_urls.append(blocked_pr.pr_info.url)
                        if not quiet:
                            # Handle multi-line messages
                            message_lines = result.message.split("\n")
                            if message_lines:
                                # Check if this is a "no changes" message (starts with ⏩)
                                if message_lines[0].startswith("⏩"):
                                    # No changes - use green for entire message
                                    console.print(
                                        f"[green]{message_lines[0]}[/green]"
                                    )
                                else:
                                    # Files were modified - use green for first line, orange for details
                                    emoji = "☑️ " if dry_run else "✅"
                                    console.print(
                                        f"[green]{emoji} {message_lines[0]}[/green]"
                                    )
                                    # Print remaining lines in orange (details of what was fixed)
                                    for line in message_lines[1:]:
                                        console.print(
                                            f"[orange1]{line}[/orange1]"
                                        )
                    elif not quiet:
                        console.print(f"[yellow]⚠️  {result.message}[/yellow]")

                    if len(result.files_modified) > 0:
                        prs_with_issues += 1

                except Exception as e:
                    if not quiet:
                        console.print(f"[red]❌ Error: {e}[/red]")

            if dry_run:
                console.print(
                    f"\n[green]☑️  Found issues in {prs_with_issues} PR(s), but no changes made[/green]"
                )
            elif prs_fixed > 0:
                console.print(f"\n[green]✅ Fixed {prs_fixed} PR(s):[/green]")
                for pr_url in fixed_pr_urls:
                    console.print(f"   • {pr_url}")
            else:
                console.print("\n[green]✅ No PRs needed fixing[/green]")

    except Exception as e:
        console.print(f"[red]Error scanning organization:[/red] {e}")
        if not quiet:
            import traceback

            console.print("[dim]" + traceback.format_exc() + "[/dim]")
        raise typer.Exit(1) from e


def _detect_max_line_length(scan_path: Path) -> int:
    """Auto-detect max_line_length from markdownlint config.

    Args:
        scan_path: Path to scan for markdownlint config

    Returns:
        Configured line length, or 80 if not configured
    """
    import json

    import yaml

    # Look for markdownlint config files in the scan path and parent directories
    current_dir = scan_path if scan_path.is_dir() else scan_path.parent
    config_names = [
        ".markdownlint.json",
        ".markdownlint.jsonc",
        ".markdownlint.yaml",
        ".markdownlint.yml",
        ".markdownlintrc",
    ]

    # Search up to 5 levels up
    for _ in range(5):
        for config_name in config_names:
            config_path = current_dir / config_name
            if config_path.exists():
                try:
                    with open(config_path, encoding="utf-8") as f:
                        if config_name.endswith((".yaml", ".yml")):
                            config = yaml.safe_load(f)
                            # yaml.safe_load returns None for empty files
                            if config is None:
                                config = {}
                        elif config_name.endswith((".json", ".jsonc", "rc")):
                            content = f.read()
                            # Simple JSONC comment removal for .jsonc files
                            if config_name.endswith(".jsonc"):
                                # Remove // comments from each line
                                lines = [
                                    line[: line.find("//")]
                                    if "//" in line
                                    else line
                                    for line in content.split("\n")
                                ]
                                content = "\n".join(lines)
                            config = json.loads(content)
                        else:
                            continue

                        # Check if MD013 has line_length configured
                        if "MD013" in config:
                            md013_config = config["MD013"]
                            if (
                                isinstance(md013_config, dict)
                                and "line_length" in md013_config
                            ):
                                line_length = md013_config["line_length"]
                                if isinstance(line_length, int):
                                    return line_length
                except (json.JSONDecodeError, yaml.YAMLError, OSError):
                    # If config can't be read, continue searching
                    pass

        # Move up one directory
        if current_dir.parent == current_dir:
            break  # Reached root
        current_dir = current_dir.parent

    # No config found or line_length not specified, return default
    return 80


def _process_file(
    file_path: Path, fix: bool = False, max_line_length: int | None = None
) -> FileResult:
    """Process a single markdown file.

    Args:
        file_path: Path to the file
        fix: Whether to fix issues
        max_line_length: Maximum line length before adding MD013 disable
                        (None = auto-detect from markdownlint config)

    Returns:
        File processing result
    """
    logger = logging.getLogger("markdown_table_fixer")
    result = FileResult(file_path=file_path)

    try:
        # Parse tables from file
        logger.debug(f"Parsing tables from {file_path}")
        parser = TableParser(file_path)
        tables = parser.parse_file()

        result.tables_found = len(tables)
        logger.debug(f"Found {len(tables)} tables in {file_path}")

        # Validate each table
        for idx, table in enumerate(tables):
            logger.debug(
                f"Validating table {idx + 1} at line {table.start_line}"
            )
            validator = TableValidator(table, max_line_length=max_line_length)
            violations = validator.validate()
            result.violations.extend(violations)
            logger.debug(
                f"Table {idx + 1}: {len(violations)} violations found (before filtering)"
            )

            if violations:
                for v in violations:
                    logger.debug(
                        f"  - {v.violation_type.value} at line {v.line_number}, col {v.column}: {v.message}"
                    )

        # Filter out violations that are in sections with disabled rules
        original_violation_count = len(result.violations)
        result.violations = filter_violations_by_disabled_rules(
            result.violations, file_path
        )
        filtered_count = original_violation_count - len(result.violations)
        if filtered_count > 0:
            logger.debug(
                f"Filtered out {filtered_count} violations due to markdownlint disable comments"
            )

        # Fix if requested
        # Always run fixer if fix=True to add MD013 comments even when no violations
        if fix:
            logger.debug(f"Applying fixes to {file_path}")
            fixer = FileFixer(file_path, max_line_length=max_line_length)
            fix_result = fixer.fix_file(tables)
            # Note: fix_result is now FileFixResult, not a list of TableFix
            # We don't track individual fixes here anymore, just log summary
            logger.debug(
                f"Applied fixes to {file_path}: {fix_result.tables_fixed} tables fixed, "
                f"{fix_result.tables_with_md013} with MD013, {fix_result.tables_with_md060} with MD060"
            )

    except (FileAccessError, TableParseError) as e:
        logger.error(f"Error processing {file_path}: {e}")
        result.error = str(e)

    return result


def _output_json_results(result: ScanResult) -> None:
    """Output results in JSON format."""
    output = {
        "files_scanned": result.files_scanned,
        "files_with_issues": result.files_with_issues,
        "files_fixed": result.files_fixed,
        "total_violations": result.total_violations,
        "total_fixes": result.total_fixes,
        "files": [
            {
                "path": str(fr.file_path),
                "tables_found": fr.tables_found,
                "violations": len(fr.violations),
                "fixes_applied": len(fr.fixes_applied),
                "error": fr.error,
            }
            for fr in result.file_results
        ],
    }
    console.print(json.dumps(output, indent=2))


def _output_text_results(result: ScanResult, quiet: bool) -> None:
    """Output results in text format."""
    if quiet:
        return

    if result.files_with_issues == 0:
        console.print("[green]✅ No issues found![/green]")
        return

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Files scanned: {result.files_scanned}")
    console.print(f"  Files with issues: {result.files_with_issues}")
    if result.files_fixed > 0:
        console.print(f"  Files fixed: {result.files_fixed}")
    console.print(f"  Total violations: {result.total_violations}")
    if result.total_fixes > 0:
        console.print(f"  Total fixes: {result.total_fixes}")
    console.print()

    # Show errors
    if result.errors:
        console.print("[bold red]Errors:[/bold red]")
        for error in result.errors[:5]:
            console.print(f"  {error}")
        if len(result.errors) > 5:
            console.print(f"  ... and {len(result.errors) - 5} more errors")
        console.print()

    # Show all files with violations or errors
    if result.files_with_issues > 0 or result.errors:
        console.print("[bold yellow]Files with issues:[/bold yellow]")

        # Collect files with issues (violations or errors)
        files_to_show = []
        for file_result in result.file_results:
            if file_result.has_violations or file_result.error:
                files_to_show.append(file_result)

        # Display each file with its issue count
        for file_result in files_to_show:
            if file_result.has_violations:
                # Count total violations for this file
                violation_count = len(file_result.violations)
                error_word = "Error" if violation_count == 1 else "Errors"

                # Get violations by rule code
                rule_counts = file_result.get_violations_by_rule()

                # Format the rule breakdown (e.g., "MD013 (2), MD060 (3)")
                rule_parts = []
                for rule in sorted(rule_counts.keys()):
                    count = rule_counts[rule]
                    rule_parts.append(f"{rule} ({count})")
                rule_breakdown = ", ".join(rule_parts)

                console.print(
                    f"  {file_result.file_path} [{violation_count} {error_word}: {rule_breakdown}]"
                )
            elif file_result.error:
                # File has a parsing or processing error
                console.print(
                    f"  {file_result.file_path} [Parse Error: {file_result.error}]"
                )


if __name__ == "__main__":
    app()
