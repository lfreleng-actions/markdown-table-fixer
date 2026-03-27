# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any

_rich_available = False

try:
    from rich.console import Console
    from rich.live import Live
    from rich.text import Text

    _rich_available = True
except ImportError:

    class Live:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def update(self, *args: Any) -> None:
            pass

    class Text:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def append(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Console:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


class ProgressTracker:
    """Real-time progress tracker for organization blocked PR checking operations."""

    def __init__(self, organization: str, show_pr_stats: bool = True):
        """Initialize progress tracker for an organization blocked PR check.

        Args:
            organization: Name of the GitHub organization being checked
            show_pr_stats: Whether to show PR analysis statistics (default True)
        """
        self.organization = organization
        self.start_time = datetime.now()
        self.console = Console() if _rich_available else None

        # Progress counters
        self.total_repositories = 0
        self.completed_repositories = 0
        self.current_repository = ""
        self.total_prs_analyzed = 0
        self.unmergeable_prs_found = 0
        self.current_operation = "Initializing..."
        self.errors_count = 0

        # Configuration
        self.show_pr_stats = show_pr_stats

        # Rate limiting tracking
        self.rate_limited = False
        self.rate_limit_reset_time: datetime | None = None

        # Rich Live display
        self.live: Live | None = None
        self.rich_available = _rich_available
        self.paused = False

        # Fallback for when Rich is not available
        self._last_display = ""

    def start(self) -> None:
        """Start the live progress display."""
        if not self.rich_available:
            return

        try:
            self.live = Live(
                self._generate_display_text(),
                console=self.console,
                refresh_per_second=2,
                transient=False,
            )
            if self.live:
                self.live.start()
        except Exception:
            # Fallback if Rich display fails (e.g., unsupported terminal)
            self.rich_available = False
            self.live = None

    def stop(self) -> None:
        """Stop the live progress display."""
        if self.live:
            with suppress(Exception):
                self.live.stop()
        # Ensure paused state is cleared when fully stopped
        self.paused = False

    def suspend(self) -> None:
        """Temporarily pause the live display to allow clean printing elsewhere."""
        if self.live and self.rich_available and not self.paused:
            with suppress(Exception):
                self.live.stop()
            self.paused = True

    def resume(self) -> None:
        """Resume the live display after it was suspended."""
        if self.rich_available and self.paused:
            with suppress(Exception):
                self.live = Live(
                    self._generate_display_text(),
                    console=self.console,
                    refresh_per_second=2,
                    transient=False,
                )
                if self.live:
                    self.live.start()
            self.paused = False

    def update_total_repositories(self, total: int) -> None:
        """Update the total number of repositories to process."""
        self.total_repositories = total
        self._refresh_display()

    def start_repository(self, repo_name: str) -> None:
        """Mark the start of processing a repository."""
        self.current_repository = repo_name
        self.current_operation = f"Getting PRs from {repo_name}"
        self._refresh_display()

    def complete_repository(self, unmergeable_count: int = 0) -> None:
        """Mark completion of a repository."""
        self.completed_repositories += 1
        self.unmergeable_prs_found += unmergeable_count
        self.current_operation = "Moving to next repository..."
        self._refresh_display()

    def update_operation(self, operation: str) -> None:
        """Update the current operation description."""
        self.current_operation = operation
        self._refresh_display()

    def analyze_pr(self, pr_number: int, repo_name: str) -> None:
        """Mark the start of analyzing a specific PR."""
        self.total_prs_analyzed += 1
        self.current_operation = f"Analyzing PR #{pr_number} in {repo_name}"
        self._refresh_display()

    def add_error(self) -> None:
        """Increment the error count."""
        self.errors_count += 1
        self._refresh_display()

    def set_rate_limited(self, reset_time: datetime) -> None:
        """Mark that we're rate limited and show countdown."""
        self.rate_limited = True
        self.rate_limit_reset_time = reset_time
        self._refresh_display()

    def clear_rate_limited(self) -> None:
        """Clear rate limiting status."""
        self.rate_limited = False
        self.rate_limit_reset_time = None
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the live display if it's active."""
        if self.live and self.rich_available and not self.paused:
            with suppress(Exception):
                self.live.update(self._generate_display_text())
        elif not self.rich_available:
            self._fallback_display()

    def _generate_display_text(self) -> Any:
        """Generate the current progress display text."""
        if not self.rich_available:
            return Text()

        text = Text()

        # Main progress line
        if self.total_repositories > 0:
            progress_pct = (
                self.completed_repositories / self.total_repositories
            ) * 100
            text.append("🔍 Checking ", style="bold blue")
            text.append(f"{self.organization} ", style="bold cyan")
            text.append(
                f"({self.completed_repositories}/{self.total_repositories} repos, ",
                style="white",
            )
            text.append(f"{progress_pct:.0f}%", style="green")
            text.append(") | ", style="white")
        else:
            text.append("🔍 Checking organization ", style="bold blue")
            text.append(f"{self.organization}", style="bold cyan")
            text.append(" (counting repositories...)", style="white")

        # Stats (only when repo count is known and PR stats are enabled)
        if self.total_repositories > 0 and self.show_pr_stats:
            text.append(
                f"{self.total_prs_analyzed} PRs analyzed | ", style="white"
            )

            if self.unmergeable_prs_found > 0:
                text.append(
                    f"{self.unmergeable_prs_found} unmergeable", style="red"
                )
            else:
                text.append(
                    f"{self.unmergeable_prs_found} unmergeable", style="green"
                )

            if self.errors_count > 0:
                text.append(f" | {self.errors_count} errors", style="yellow")
        elif self.total_repositories > 0 and not self.show_pr_stats:
            # Show errors even when PR stats are disabled
            if self.errors_count > 0:
                text.append(f"{self.errors_count} errors", style="yellow")

        text.append("\n")

        # Current operation line
        if self.rate_limited and self.rate_limit_reset_time:
            remaining = self.rate_limit_reset_time - datetime.now()
            if remaining.total_seconds() > 0:
                text.append(
                    f"⏳ Rate limited - waiting {remaining.seconds}s",
                    style="yellow",
                )
            else:
                text.append("⚡ Rate limit reset - resuming...", style="green")
        else:
            text.append(f"📋 {self.current_operation}", style="dim white")

        # Elapsed time
        elapsed = datetime.now() - self.start_time
        text.append(
            f"\n⏱️  Elapsed: {self._format_duration(elapsed)}", style="dim blue"
        )

        return text

    def _fallback_display(self) -> None:
        """Fallback display method for when Rich is not available."""
        # Generate simple text display
        if self.total_repositories > 0:
            progress_pct = (
                self.completed_repositories / self.total_repositories
            ) * 100
            if self.show_pr_stats:
                progress_line = f"🔍 Checking {self.organization} ({self.completed_repositories}/{self.total_repositories} repos, {progress_pct:.0f}%) | {self.total_prs_analyzed} PRs analyzed | {self.unmergeable_prs_found} unmergeable"
            else:
                progress_line = f"🔍 Checking {self.organization} ({self.completed_repositories}/{self.total_repositories} repos, {progress_pct:.0f}%)"
            if self.errors_count > 0:
                progress_line += f" | {self.errors_count} errors"
        else:
            progress_line = f"🔍 Checking organization {self.organization} (counting repositories...)"

        operation_line = f"📋 {self.current_operation}"
        elapsed = datetime.now() - self.start_time
        time_line = f"⏱️  Elapsed: {self._format_duration(elapsed)}"

        current_display = f"{progress_line}\n{operation_line}\n{time_line}"

        # Only print if display has changed to avoid spam
        if current_display != self._last_display:
            print(f"\r{current_display}\n", end="", flush=True)
            self._last_display = current_display

    def _format_duration(self, duration: timedelta) -> str:
        """Format a duration for display."""
        total_seconds = int(duration.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        if minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the checking progress."""
        elapsed = datetime.now() - self.start_time

        return {
            "organization": self.organization,
            "total_repositories": self.total_repositories,
            "completed_repositories": self.completed_repositories,
            "total_prs_analyzed": self.total_prs_analyzed,
            "unmergeable_prs_found": self.unmergeable_prs_found,
            "errors_count": self.errors_count,
            "elapsed_time": self._format_duration(elapsed),
            "rate_limited": self.rate_limited,
        }


class MergeProgressTracker(ProgressTracker):
    """Specialized progress tracker for merge operations."""

    def __init__(self, organization: str, is_close_operation: bool = False):
        super().__init__(organization)
        self.similar_prs_found = 0
        self.prs_merged = 0
        self.merge_failures = 0
        self.prs_closed = 0
        self.is_close_operation = is_close_operation

    def add_similar_pr(self) -> None:
        """Mark that a similar PR was found."""
        self.similar_prs_found += 1
        self._refresh_display()

    def merge_success(self) -> None:
        """Mark a successful merge."""
        self.prs_merged += 1
        self._refresh_display()

    def merge_failure(self) -> None:
        """Mark a failed merge."""
        self.merge_failures += 1
        self._refresh_display()

    def increment_closed(self) -> None:
        """Mark a successful close."""
        self.prs_closed += 1
        self._refresh_display()

    def _generate_display_text(self) -> Any:
        """Generate merge-specific display text."""
        if not self.rich_available:
            return Text()

        text = Text()

        # Main progress line for merge/close operations
        if self.total_repositories > 0:
            progress_pct = (
                self.completed_repositories / self.total_repositories
            ) * 100
            operation_icon = "🚪" if self.is_close_operation else "🔀"
            operation_text = (
                "Searching for similar PRs"
                if not self.is_close_operation
                else "Searching for similar PRs"
            )
            text.append(
                f"{operation_icon} {operation_text} ", style="bold blue"
            )
            text.append(
                f"({self.completed_repositories}/{self.total_repositories} repos, ",
                style="white",
            )
            text.append(f"{progress_pct:.0f}%", style="green")
            text.append(") | ", style="white")
        # Special heading when examining the source PR before repo enumeration
        elif "Getting source PR details" in (self.current_operation or ""):
            text.append(
                "🔍 Examining source pull request in ", style="bold blue"
            )
            text.append(f"{self.organization}", style="bold cyan")
        else:
            operation_icon = "🚪" if self.is_close_operation else "🔀"
            text.append(
                f"{operation_icon} Analyzing PRs in ", style="bold blue"
            )
            text.append(f"{self.organization}", style="bold cyan")

        # Stats for merge operations (only when repo count is known)
        if self.total_repositories > 0:
            text.append(
                f"{self.total_prs_analyzed} PRs analyzed", style="white"
            )
            if self.errors_count > 0:
                text.append(f" | {self.errors_count} errors", style="yellow")

        text.append("\n")

        # Current operation line
        if self.rate_limited and self.rate_limit_reset_time:
            remaining = self.rate_limit_reset_time - datetime.now()
            if remaining.total_seconds() > 0:
                text.append(
                    f"⏳ Rate limited - waiting {remaining.seconds}s",
                    style="yellow",
                )
            else:
                text.append("⚡ Rate limit reset - resuming...", style="green")
        else:
            text.append(f"📋 {self.current_operation}", style="dim white")

        # Elapsed time
        elapsed = datetime.now() - self.start_time
        text.append(
            f"\n⏱️  Elapsed: {self._format_duration(elapsed)}", style="dim blue"
        )

        return text

    def get_summary(self) -> dict[str, Any]:
        """Get merge-specific summary."""
        summary = super().get_summary()
        summary.update(
            {
                "similar_prs_found": self.similar_prs_found,
                "prs_merged": self.prs_merged,
                "merge_failures": self.merge_failures,
                "prs_closed": self.prs_closed,
            }
        )
        return summary


class DummyProgressTracker:
    """A no-op progress tracker for when progress display is disabled."""

    def __init__(self, organization: str):
        self.organization = organization

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update_total_repositories(self, total: int) -> None:
        pass

    def start_repository(self, repo_name: str) -> None:
        pass

    def complete_repository(self, unmergeable_count: int = 0) -> None:
        pass

    def update_operation(self, operation: str) -> None:
        pass

    def analyze_pr(self, pr_number: int, repo_name: str) -> None:
        pass

    def add_error(self) -> None:
        pass

    def set_rate_limited(self, reset_time: datetime) -> None:
        pass

    def clear_rate_limited(self) -> None:
        pass

    def found_similar_pr(self) -> None:
        pass

    def merge_success(self) -> None:
        pass

    def merge_failure(self) -> None:
        pass

    def increment_closed(self) -> None:
        pass

    def get_summary(self) -> dict[str, Any]:
        return {"organization": self.organization}
