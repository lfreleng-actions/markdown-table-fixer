# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Scanner for identifying pull requests with markdown table issues."""

# aislop-ignore-file complexity/file-too-large -- cohesive PR scanner module

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from .github_client import GitHubClient
    from .progress_tracker import ProgressTracker

from .graphql_queries import ORG_REPOS_ONLY, REPO_OPEN_PRS_PAGE

# GitHub API tuning defaults - optimized for performance and rate limit compliance
# These match dependamerge's proven values
DEFAULT_PRS_PAGE_SIZE = 30  # Pull requests per GraphQL page
DEFAULT_FILES_PAGE_SIZE = 50  # Files per pull request
DEFAULT_COMMENTS_PAGE_SIZE = 10  # Comments per pull request
DEFAULT_CONTEXTS_PAGE_SIZE = 20  # Status contexts per pull request


class PRScanner:
    """Scanner for finding PRs with markdown table formatting issues."""

    def __init__(
        self,
        client: GitHubClient,
        progress_tracker: ProgressTracker | None = None,
        max_repo_tasks: int = 8,
        max_page_tasks: int = 16,
    ):
        """Initialize PR scanner.

        Args:
            client: GitHub API client
            progress_tracker: Optional progress tracker for UI updates
            max_repo_tasks: Max concurrent repository scans (default: 8, matches dependamerge)
            max_page_tasks: Max concurrent page fetches (default: 16, matches dependamerge)
        """
        self.client = client
        self.logger = logging.getLogger(__name__)
        self.progress_tracker = progress_tracker
        self._max_repo_tasks = max_repo_tasks
        self._max_page_tasks = max_page_tasks
        self._repo_semaphore = asyncio.Semaphore(self._max_repo_tasks)
        self._page_semaphore = asyncio.Semaphore(self._max_page_tasks)

    async def scan_organization(
        self,
        org: str,
        *,
        include_drafts: bool = False,
    ) -> AsyncIterator[tuple[str, str, dict[str, Any]]]:
        """Scan all repositories in an organization for PRs with markdown/lint failures.

        Uses dependamerge's proven approach:
        1. Count total repositories
        2. Fetch repos (without PRs to keep queries light)
        3. For each repo, fetch PRs with status checks
        4. Process repos with bounded parallelism

        Args:
            org: Organization name
            include_drafts: Whether to include draft PRs

        Yields:
            Tuple of (owner, repo, pr_data) for each PR with failing markdown/lint checks
        """
        # First pass: count repositories for accurate progress
        if self.progress_tracker:
            total_repos = await self._count_org_repositories(org)
            self.progress_tracker.update_total_repositories(total_repos)

        # Collect all repos first
        repos = []
        async for repo in self._iter_org_repositories(org):
            repos.append(repo)

        tasks = [
            asyncio.create_task(self._process_repo(repo, include_drafts))
            for repo in repos
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    self.logger.error(
                        f"Unhandled error during repository processing: {result}"
                    )
                    continue
                # Yield each PR found
                for owner, repo_name, pr_data in result:
                    yield owner, repo_name, pr_data

    async def _process_repo(
        self, repo_node: dict[str, Any], include_drafts: bool
    ) -> list[tuple[str, str, dict[str, Any]]]:
        """Fetch and analyze one repository's PRs for markdown/lint failures."""
        async with self._repo_semaphore:
            results: list[tuple[str, str, dict[str, Any]]] = []
            repo_full_name = repo_node.get("nameWithOwner", "")
            if not repo_full_name or "/" not in repo_full_name:
                return results

            owner, repo_name = repo_full_name.split("/", 1)

            if self.progress_tracker:
                self.progress_tracker.start_repository(repo_full_name)

            try:
                prs_nodes = await self._fetch_all_repo_prs(
                    owner, repo_name, repo_full_name
                )
                results, blocked_count = self._collect_failing_prs(
                    prs_nodes,
                    owner,
                    repo_name,
                    repo_full_name,
                    include_drafts,
                )

                if self.progress_tracker:
                    self.progress_tracker.complete_repository(blocked_count)

            except Exception as e:
                self.logger.error(
                    f"Fatal error scanning repository {repo_full_name}: {e}"
                )
                if self.progress_tracker:
                    self.progress_tracker.add_error()

            return results

    async def _fetch_all_repo_prs(
        self, owner: str, repo_name: str, repo_full_name: str
    ) -> list[dict[str, Any]]:
        """Fetch every open PR node for a repo, following pagination."""
        try:
            (
                prs_nodes,
                page_info,
            ) = await self._fetch_repo_prs_first_page(owner, repo_name)
        except Exception as e:
            self.logger.error(
                f"Error fetching PRs for repository {repo_full_name}: {e}"
            )
            raise

        # Fetch additional pages if needed
        if page_info.get("hasNextPage"):
            end_cursor = page_info.get("endCursor")
            try:
                async for pr_node in self._iter_repo_prs_pages(
                    owner, repo_name, end_cursor
                ):
                    prs_nodes.append(pr_node)
            except Exception as e:
                self.logger.error(
                    f"Error fetching additional PR pages for repository {repo_full_name}: {e}"
                )
                raise

        return prs_nodes

    def _collect_failing_prs(
        self,
        prs_nodes: list[dict[str, Any]],
        owner: str,
        repo_name: str,
        repo_full_name: str,
        include_drafts: bool,
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], int]:
        """Return (results, blocked_count) for PRs failing markdown/lint checks."""
        results: list[tuple[str, str, dict[str, Any]]] = []
        blocked_count = 0
        for pr_node in prs_nodes:
            # Skip draft PRs unless explicitly included
            if pr_node.get("isDraft", False) and not include_drafts:
                continue

            if self.progress_tracker:
                pr_number = pr_node.get("number", 0)
                self.progress_tracker.analyze_pr(pr_number, repo_full_name)

            try:
                # Check if PR has failing markdown/lint checks
                failing_checks = self._extract_failing_checks(pr_node)
                has_markdown_lint_failures = any(
                    self._is_markdown_or_lint_check(check_name)
                    for check_name in failing_checks
                )

                if has_markdown_lint_failures:
                    blocked_count += 1
                    # Convert GraphQL PR node to REST API-like structure
                    pr_data = self._graphql_pr_to_rest_format(
                        pr_node, owner, repo_name
                    )
                    results.append((owner, repo_name, pr_data))
            except Exception as e:
                pr_num = pr_node.get("number", "unknown")
                self.logger.error(
                    f"Error analyzing PR #{pr_num} in repository {repo_full_name}: {e}"
                )
                # Continue processing other PRs
                continue

        return results, blocked_count

    async def _count_org_repositories(self, org: str) -> int:
        """Count total repositories using a lightweight query (no PR data).

        This matches dependamerge's proven approach using ORG_REPOS_ONLY.

        Args:
            org: Organization name

        Returns:
            Total number of non-archived repositories
        """
        count = 0
        cursor: str | None = None

        while True:
            data = await self.client.graphql(
                ORG_REPOS_ONLY, {"org": org, "reposCursor": cursor}
            )
            repos = ((data or {}).get("organization") or {}).get(
                "repositories"
            ) or {}
            nodes: list[dict[str, Any]] = repos.get("nodes", []) or []

            # Count non-archived repos
            for repo in nodes:
                if repo.get("isArchived"):
                    continue
                count += 1

            page_info = repos.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        return count

    async def _iter_org_repositories(
        self, org: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate repositories in an organization using lightweight query.

        This matches dependamerge's approach - fetch repo names only, no PR data.

        Args:
            org: Organization name

        Yields:
            Repository nodes (non-archived)
        """
        cursor: str | None = None

        while True:
            variables = {"org": org, "reposCursor": cursor}
            data = await self.client.graphql(ORG_REPOS_ONLY, variables)
            repos = ((data or {}).get("organization") or {}).get(
                "repositories"
            ) or {}
            nodes: list[dict[str, Any]] = repos.get("nodes", []) or []

            for repo in nodes:
                # Skip archived repositories
                if repo.get("isArchived"):
                    continue
                yield repo

            page_info = repos.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

    async def _fetch_repo_prs_first_page(
        self, owner: str, name: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch the first page of PRs for a repository.

        This matches dependamerge's approach with parameterized page sizes.

        Args:
            owner: Repository owner
            name: Repository name

        Returns:
            Tuple of (list of PR nodes, page_info dict)
        """
        variables = {
            "owner": owner,
            "name": name,
            "prsCursor": None,
            "prsPageSize": DEFAULT_PRS_PAGE_SIZE,
            "filesPageSize": DEFAULT_FILES_PAGE_SIZE,
            "commentsPageSize": DEFAULT_COMMENTS_PAGE_SIZE,
            "contextsPageSize": DEFAULT_CONTEXTS_PAGE_SIZE,
        }

        async with self._page_semaphore:
            data = await self.client.graphql(REPO_OPEN_PRS_PAGE, variables)
        repo = (data or {}).get("repository") or {}
        prs = repo.get("pullRequests") or {}
        nodes: list[dict[str, Any]] = prs.get("nodes", []) or []
        page_info = prs.get("pageInfo") or {}

        return nodes, page_info

    async def _iter_repo_prs_pages(
        self, owner: str, name: str, cursor: str | None
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate additional pages of PRs for a repository.

        This matches dependamerge's pagination pattern with parameterized page sizes.

        Args:
            owner: Repository owner
            name: Repository name
            cursor: Starting cursor for pagination

        Yields:
            PR nodes
        """
        prs_cursor = cursor
        while prs_cursor:
            variables = {
                "owner": owner,
                "name": name,
                "prsCursor": prs_cursor,
                "prsPageSize": DEFAULT_PRS_PAGE_SIZE,
                "filesPageSize": DEFAULT_FILES_PAGE_SIZE,
                "commentsPageSize": DEFAULT_COMMENTS_PAGE_SIZE,
                "contextsPageSize": DEFAULT_CONTEXTS_PAGE_SIZE,
            }

            async with self._page_semaphore:
                data = await self.client.graphql(REPO_OPEN_PRS_PAGE, variables)
            repo = (data or {}).get("repository") or {}
            prs = repo.get("pullRequests") or {}
            nodes: list[dict[str, Any]] = prs.get("nodes", []) or []

            for pr in nodes:
                yield pr

            page_info = prs.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            prs_cursor = page_info.get("endCursor")

    def _extract_failing_checks(self, pr: dict[str, Any]) -> list[str]:
        """Extract failing check names from PR statusCheckRollup.

        This is the same logic as dependamerge uses.

        Args:
            pr: PR data from GraphQL with statusCheckRollup

        Returns:
            List of failing check names
        """
        failing: list[str] = []

        commits = (pr.get("commits") or {}).get("nodes", []) or []
        if not commits:
            return failing

        commit = (commits[0] or {}).get("commit") or {}
        rollup = commit.get("statusCheckRollup") or {}
        contexts = (rollup.get("contexts") or {}).get("nodes", []) or []

        for ctx in contexts:
            typ = ctx.get("__typename")
            if typ == "CheckRun":
                # Consider failure, cancelled, or timed_out as failing
                conclusion = (ctx.get("conclusion") or "").lower()
                if conclusion in (
                    "failure",
                    "cancelled",
                    "timed_out",
                    "action_required",
                ):
                    name = ctx.get("name") or ""
                    if name:
                        failing.append(name)
            elif typ == "StatusContext":
                # StatusContext uses state instead of conclusion
                state = (ctx.get("state") or "").upper()
                if state in ("FAILURE", "ERROR"):
                    context = ctx.get("context") or ""
                    if context:
                        failing.append(context)

        return failing

    def _is_markdown_or_lint_check(self, check_name: str) -> bool:
        """Check if a check name is related to markdown or linting.

        Args:
            check_name: Name or context of the check

        Returns:
            True if check is related to markdown/linting
        """
        check_lower = check_name.lower()
        keywords = [
            "markdown",
            "lint",
            "pre-commit",
            "table",
            "format",
            "markdownlint",
        ]
        return any(keyword in check_lower for keyword in keywords)

    def _graphql_pr_to_rest_format(
        self, pr_node: dict[str, Any], owner: str, repo: str
    ) -> dict[str, Any]:
        """Convert GraphQL PR node to REST API-like format.

        This ensures downstream code that expects REST API structure continues to work.

        Args:
            pr_node: PR node from GraphQL
            owner: Repository owner
            repo: Repository name

        Returns:
            PR data in REST API format
        """
        author = pr_node.get("author") or {}
        head_repo = pr_node.get("headRepository") or {}
        base_repo = pr_node.get("baseRepository") or {}

        return {
            "number": pr_node.get("number"),
            "title": pr_node.get("title", ""),
            "body": pr_node.get("body", ""),
            "html_url": pr_node.get("url", ""),
            "url": f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_node.get('number')}",
            "user": {
                "login": author.get("login", ""),
            },
            "draft": pr_node.get("isDraft", False),
            "head": {
                "ref": pr_node.get("headRefName", ""),
                "sha": pr_node.get("headRefOid", ""),
                "repo": (
                    {
                        "full_name": head_repo.get("nameWithOwner", ""),
                        "clone_url": head_repo.get("url", ""),
                    }
                    if head_repo
                    else None
                ),
            },
            "base": {
                "ref": pr_node.get("baseRefName", ""),
                "repo": (
                    {
                        "full_name": base_repo.get("nameWithOwner", ""),
                        "clone_url": base_repo.get("url", ""),
                    }
                    if base_repo
                    else None
                ),
            },
            "mergeable": pr_node.get("mergeable"),
            "mergeable_state": pr_node.get("mergeStateStatus", "").lower(),
            "merge_state_status": pr_node.get("mergeStateStatus", ""),
            "created_at": pr_node.get("createdAt", ""),
            "updated_at": pr_node.get("updatedAt", ""),
            "maintainer_can_modify": pr_node.get("maintainerCanModify", False),
            "is_cross_repository": pr_node.get("isCrossRepository", False),
        }
