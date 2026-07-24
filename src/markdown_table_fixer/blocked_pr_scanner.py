# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""
Blocked PR scanner using dependamerge's GitHubService.

This module wraps dependamerge's PR scanning functionality to provide
consistent blocked PR detection across both tools.
"""

import asyncio
from collections.abc import AsyncIterator
import logging
from typing import Any

from dependamerge.github_service import GitHubService
from dependamerge.models import UnmergeablePR

from .progress_tracker import ProgressTracker


class BlockedPRScanner:
    """Scanner for blocked/unmergeable pull requests using dependamerge logic."""

    def __init__(
        self,
        token: str,
        progress_tracker: ProgressTracker | None = None,
        max_repo_tasks: int = 10,
    ):
        """Initialize the blocked PR scanner.

        Args:
            token: GitHub authentication token
            progress_tracker: Optional progress tracker for UI updates
            max_repo_tasks: Maximum number of repositories to process concurrently
        """
        self.token = token
        self.progress_tracker = progress_tracker
        self.max_repo_tasks = max_repo_tasks
        self.logger = logging.getLogger(__name__)

        self.service = GitHubService(
            token=token,
            progress_tracker=progress_tracker,
            max_repo_tasks=max_repo_tasks,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.service.close()

    async def scan_organization_for_blocked_prs(
        self,
        organization: str,
        include_drafts: bool = False,
    ) -> AsyncIterator[tuple[str, str, dict[str, Any], UnmergeablePR]]:
        """Scan an organization for blocked/unmergeable pull requests.

        This method uses dependamerge's GitHubService to analyze PRs and only
        yields those that are truly blocked (have merge conflicts, failing checks,
        behind base, etc.). This ensures consistency with dependamerge's reporting.

        Args:
            organization: Organization name to scan
            include_drafts: Whether to include draft PRs (default False)

        Yields:
            Tuples of (owner, repo_name, pr_data, unmergeable_pr) where:
            - owner: Repository owner
            - repo_name: Repository name
            - pr_data: Raw PR data dict from GraphQL
            - unmergeable_pr: UnmergeablePR model with blocking reasons
        """
        self.logger.debug(
            f"Starting blocked PR scan of organization: {organization}"
        )

        # Start progress tracker if available
        if self.progress_tracker:
            self.progress_tracker.start()

        try:
            # Use dependamerge's scan_organization which already:
            # 1. Counts repositories
            # 2. Paginates through PRs
            # 3. Analyzes blocking conditions
            # 4. Tracks progress correctly
            scan_result = await self.service.scan_organization(
                organization, include_drafts=include_drafts
            )
        finally:
            if self.progress_tracker:
                self.progress_tracker.stop()

        # Display summary
        if self.progress_tracker:
            from rich.console import Console

            console = Console()
            console.print(
                f"\n✅ Scan completed\n"
                f"📊 Found {len(scan_result.unmergeable_prs)} blocked PRs "
                f"out of {scan_result.total_prs} total PRs across {scan_result.scanned_repositories} repositories"
            )
        else:
            self.logger.info(
                f"Scan complete: found {len(scan_result.unmergeable_prs)} blocked PRs "
                f"out of {scan_result.total_prs} total PRs across {scan_result.scanned_repositories} repositories"
            )

        # Now we need to fetch the full PR data for each unmergeable PR
        # to provide it in the same format as the old scanner
        for unmergeable_pr in scan_result.unmergeable_prs:
            # Split repository name
            parts = unmergeable_pr.repository.split("/", 1)
            if len(parts) != 2:
                self.logger.warning(
                    f"Invalid repository format: {unmergeable_pr.repository}"
                )
                continue

            owner, repo_name = parts

            # Create a minimal pr_data dict that matches what the old scanner returned
            # This is primarily for compatibility with existing code
            pr_data = {
                "number": unmergeable_pr.pr_number,
                "title": unmergeable_pr.title,
                "author": {"login": unmergeable_pr.author},
                "url": unmergeable_pr.url,
                "createdAt": unmergeable_pr.created_at,
                "updatedAt": unmergeable_pr.updated_at,
                # Include blocking information for backward compatibility
                "_unmergeable_reasons": [
                    {
                        "type": reason.type,
                        "description": reason.description,
                        "details": reason.details,
                    }
                    for reason in unmergeable_pr.reasons
                ],
            }

            yield owner, repo_name, pr_data, unmergeable_pr

    async def scan_organization_all_prs(
        self,
        organization: str,
        include_drafts: bool = False,
    ) -> AsyncIterator[tuple[str, str, dict[str, Any], bool]]:
        """Scan an organization for ALL pull requests, marking which are blocked.

        This is useful when you want to process all PRs but need to know which
        ones are blocked.

        Args:
            organization: Organization name to scan
            include_drafts: Whether to include draft PRs

        Yields:
            Tuples of (owner, repo_name, pr_data, is_blocked) where:
            - owner: Repository owner
            - repo_name: Repository name
            - pr_data: Raw PR data dict from GraphQL
            - is_blocked: Boolean indicating if PR is blocked
        """
        # Fetching every PR (not just blocked ones) needs the lower-level
        # iteration methods; only blocked-only scanning is supported today.
        raise NotImplementedError(
            "Scanning all PRs (not just blocked) is not yet implemented. "
            "Use scan_organization_for_blocked_prs() for blocked-only scanning."
        )

    def is_pr_blocked(self, pr: dict[str, Any]) -> tuple[bool, list[str]]:
        """Check if a PR is blocked from merging (synchronous wrapper).

        This method provides backward compatibility with the old scanner interface.
        It uses the same logic as dependamerge's _analyze_pr_node.

        Args:
            pr: PR data from GraphQL

        Returns:
            Tuple of (is_blocked, list of blocking reasons as strings)
        """
        # Use asyncio to call the async version
        return asyncio.run(self._is_pr_blocked_async(pr))

    async def _is_pr_blocked_async(
        self, pr: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Async version of is_pr_blocked.

        Args:
            pr: PR data from GraphQL

        Returns:
            Tuple of (is_blocked, list of blocking reasons as strings)
        """
        # Use dependamerge's _analyze_pr_node to check if PR is blocked
        result = await self.service._analyze_pr_node(
            repo_full_name="temp/repo",  # Not used for just checking blocked status
            pr=pr,
            include_drafts=False,
        )

        if result is None:
            return False, []

        reasons = [reason.description for reason in result.reasons]
        return True, reasons
