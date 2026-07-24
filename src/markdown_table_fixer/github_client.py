# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""GitHub API client for repository and PR operations."""

from __future__ import annotations

import base64
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .exceptions import FileAccessError


class GitHubClient:
    """Client for GitHub API operations."""

    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token
            base_url: GitHub API base URL
        """
        self.token = token
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def __aenter__(self) -> GitHubClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make an API request with retry logic.

        Args:
            method: HTTP method
            endpoint: API endpoint path
            **kwargs: Additional arguments for httpx request

        Returns:
            Response JSON data

        Raises:
            FileAccessError: If request fails
        """
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method,
                    url,
                    headers=self.headers,
                    **kwargs,
                )
                response.raise_for_status()
                result: dict[str, Any] | list[dict[str, Any]] = response.json()
                return result
            except httpx.HTTPStatusError as e:
                msg = f"GitHub API error: {e.response.status_code} - {e.response.text}"
                raise FileAccessError(msg) from e
            except httpx.RequestError as e:
                msg = f"Request failed: {e}"
                raise FileAccessError(msg) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _graphql_request(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GraphQL API request with retry logic.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data

        Raises:
            FileAccessError: If request fails
        """
        url = "https://api.github.com/graphql"
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                json_response = response.json()
                result: dict[str, Any] = (
                    json_response if isinstance(json_response, dict) else {}
                )

                if "errors" in result:
                    errors = result["errors"]
                    msg = f"GraphQL errors: {errors}"
                    raise FileAccessError(msg)

                data: dict[str, Any] = result.get("data", {})
                return data
            except httpx.HTTPStatusError as e:
                msg = f"GitHub API error: {e.response.status_code} - {e.response.text}"
                raise FileAccessError(msg) from e
            except httpx.RequestError as e:
                msg = f"Request failed: {e}"
                raise FileAccessError(msg) from e

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data

        Raises:
            FileAccessError: If request fails
        """
        result: dict[str, Any] = await self._graphql_request(query, variables)
        return result

    async def get_pr_files(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """Get files changed in a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number

        Returns:
            List of changed files
        """
        files = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
        )
        return files if isinstance(files, list) else []

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str:
        """Get file content from a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            ref: Git ref (branch/commit SHA)

        Returns:
            Decoded file content

        Raises:
            FileAccessError: If file cannot be retrieved
        """
        result = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
        )

        if not isinstance(result, dict):
            msg = f"Unexpected response type for file content: {type(result)}"
            raise FileAccessError(msg)

        content_b64 = result.get("content", "")
        if not content_b64:
            return ""

        try:
            return base64.b64decode(content_b64).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as e:
            msg = f"Failed to decode file content: {e}"
            raise FileAccessError(msg) from e

    # aislop-ignore-next-line complexity/too-many-params -- GitHub contents API shape
    async def update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str,
    ) -> dict[str, Any]:
        """Update a file in a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            content: New file content
            message: Commit message
            branch: Branch name
            sha: Current file SHA (for conflict detection)

        Returns:
            Commit data
        """
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        result = await self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            json={
                "message": message,
                "content": content_b64,
                "branch": branch,
                "sha": sha,
            },
        )
        return result if isinstance(result, dict) else {}

    async def get_rate_limit(self) -> dict[str, Any]:
        """Get current API rate limit status.

        Returns:
            Rate limit information
        """
        result = await self._request("GET", "/rate_limit")
        return result if isinstance(result, dict) else {}

    async def batch_update_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: list[dict[str, str]],
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> dict[str, Any]:
        """Update multiple files in a single commit using Git Data API.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name
            files: List of dicts with 'path' and 'content' keys
            message: Commit message
            author_name: Commit author name (optional)
            author_email: Commit author email (optional)

        Returns:
            Commit data
        """
        ref_result = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/ref/heads/{branch}",
        )
        if not isinstance(ref_result, dict):
            msg = "Failed to get branch reference"
            raise FileAccessError(msg)

        base_commit_sha = ref_result["object"]["sha"]

        commit_result = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/commits/{base_commit_sha}",
        )
        if not isinstance(commit_result, dict):
            msg = "Failed to get base commit"
            raise FileAccessError(msg)

        base_tree_sha = commit_result["tree"]["sha"]

        tree_items = []
        for file_info in files:
            path = file_info["path"]
            content = file_info["content"]

            blob_result = await self._request(
                "POST",
                f"/repos/{owner}/{repo}/git/blobs",
                json={
                    "content": content,
                    "encoding": "utf-8",
                },
            )
            if not isinstance(blob_result, dict):
                msg = f"Failed to create blob for {path}"
                raise FileAccessError(msg)

            blob_sha = blob_result["sha"]

            tree_items.append(
                {
                    "path": path,
                    "mode": "100644",  # Regular file
                    "type": "blob",
                    "sha": blob_sha,
                }
            )

        tree_result = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            json={
                "base_tree": base_tree_sha,
                "tree": tree_items,
            },
        )
        if not isinstance(tree_result, dict):
            msg = "Failed to create tree"
            raise FileAccessError(msg)

        new_tree_sha = tree_result["sha"]

        commit_payload: dict[str, Any] = {
            "message": message,
            "tree": new_tree_sha,
            "parents": [base_commit_sha],
        }

        # Add author information if provided
        if author_name and author_email:
            commit_payload["author"] = {
                "name": author_name,
                "email": author_email,
            }
            # Use same identity for committer to ensure DCO compliance
            commit_payload["committer"] = {
                "name": author_name,
                "email": author_email,
            }

        commit_create_result = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json=commit_payload,
        )
        if not isinstance(commit_create_result, dict):
            msg = "Failed to create commit"
            raise FileAccessError(msg)

        new_commit_sha = commit_create_result["sha"]

        update_result = await self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{branch}",
            json={
                "sha": new_commit_sha,
                "force": False,  # Don't force update
            },
        )

        return update_result if isinstance(update_result, dict) else {}

    async def create_comment(
        self, owner: str, repo: str, pr_number: int, body: str
    ) -> dict[str, Any]:
        """Create a comment on a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            body: Comment body

        Returns:
            Comment data
        """
        result = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        return result if isinstance(result, dict) else {}
