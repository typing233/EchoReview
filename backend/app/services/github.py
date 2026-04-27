"""
GitHub API client for OAuth, PR collection, and webhook management.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import httpx
from app.config import settings
import structlog

logger = structlog.get_logger()

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_user(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{GITHUB_API_BASE}/user", headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def get_repositories(self, page: int = 1, per_page: int = 100) -> List[Dict[str, Any]]:
        """List repositories accessible to the authenticated user."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/user/repos",
                headers=self.headers,
                params={"page": page, "per_page": per_page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "closed",
        page: int = 1,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                headers=self.headers,
                params={"state": state, "page": page, "per_page": per_page, "sort": "updated", "direction": "desc"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Get the unified diff for a PR."""
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.text

    async def get_pull_request_files(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get files changed in a PR."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=self.headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_review_comments(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get review comments (line-level) on a PR."""
        comments = []
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                    headers=self.headers,
                    params={"page": page, "per_page": 100},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                comments.extend(data)
                if len(data) < 100:
                    break
                page += 1
        return comments

    async def get_issue_comments(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get general (non-line) comments on a PR."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments",
                headers=self.headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pr_reviews(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get review objects (approved/requested changes) for a PR."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                headers=self.headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Get commits in a PR."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/commits",
                headers=self.headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_commit_diff(self, owner: str, repo: str, sha: str) -> str:
        """Get diff for a specific commit."""
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{sha}",
                headers=headers,
            )
            resp.raise_for_status()
            return resp.text

    async def create_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        commit_id: str,
        path: str,
        line: int,
        side: str = "RIGHT",
    ) -> Dict[str, Any]:
        """Post a review comment on a specific line."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                headers=self.headers,
                json={"body": body, "commit_id": commit_id, "path": path, "line": line, "side": side},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        body: str,
        comments: List[Dict[str, Any]],
        event: str = "COMMENT",
    ) -> Dict[str, Any]:
        """Submit a batch review with multiple comments."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                headers=self.headers,
                json={"commit_id": commit_id, "body": body, "event": event, "comments": comments},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        webhook_url: str,
        secret: str,
    ) -> Dict[str, Any]:
        """Register a webhook for PR events."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/hooks",
                headers=self.headers,
                json={
                    "name": "web",
                    "active": True,
                    "events": ["pull_request", "pull_request_review", "pull_request_review_comment"],
                    "config": {
                        "url": webhook_url,
                        "content_type": "json",
                        "secret": secret,
                        "insecure_ssl": "0",
                    },
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_webhook(self, owner: str, repo: str, hook_id: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/hooks/{hook_id}",
                headers=self.headers,
            )
            resp.raise_for_status()


def get_oauth_url(state: str) -> str:
    """Build GitHub OAuth authorization URL."""
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "repo,read:org,read:user,user:email",
        "state": state,
    }
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GITHUB_OAUTH_URL}?{param_str}"


async def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """Exchange OAuth code for access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
