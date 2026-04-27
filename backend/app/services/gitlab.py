"""
GitLab API client for OAuth, PR (Merge Request) collection, and webhook management.
"""
import hashlib
import hmac
from typing import Optional, List, Dict, Any
import httpx
from app.config import settings
import structlog

logger = structlog.get_logger()

GITLAB_OAUTH_URL = "/oauth/authorize"
GITLAB_TOKEN_URL = "/oauth/token"


class GitLabClient:
    def __init__(self, access_token: str, base_url: Optional[str] = None):
        self.access_token = access_token
        self.base_url = (base_url or settings.gitlab_base_url).rstrip("/")
        self.api_base = f"{self.base_url}/api/v4"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def get_user(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.api_base}/user", headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def get_repositories(self, page: int = 1, per_page: int = 100) -> List[Dict[str, Any]]:
        """List projects accessible to the authenticated user."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/projects",
                headers=self.headers,
                params={
                    "page": page,
                    "per_page": per_page,
                    "membership": True,
                    "order_by": "last_activity_at",
                    "sort": "desc",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_merge_requests(
        self,
        project_id: str,
        state: str = "merged",
        page: int = 1,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/projects/{project_id}/merge_requests",
                headers=self.headers,
                params={"state": state, "page": page, "per_page": per_page, "order_by": "updated_at", "sort": "desc"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_merge_request(self, project_id: str, mr_iid: int) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_merge_request_changes(self, project_id: str, mr_iid: int) -> Dict[str, Any]:
        """Get file changes (diff) for a MR."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}/changes",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_merge_request_notes(self, project_id: str, mr_iid: int) -> List[Dict[str, Any]]:
        """Get notes (comments) on a MR."""
        notes = []
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}/notes",
                    headers=self.headers,
                    params={"page": page, "per_page": 100, "sort": "asc"},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                notes.extend(data)
                if len(data) < 100:
                    break
                page += 1
        return notes

    async def get_merge_request_discussions(self, project_id: str, mr_iid: int) -> List[Dict[str, Any]]:
        """Get discussion threads (with line context) on a MR."""
        discussions = []
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}/discussions",
                    headers=self.headers,
                    params={"page": page, "per_page": 100},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                discussions.extend(data)
                if len(data) < 100:
                    break
                page += 1
        return discussions

    async def get_merge_request_commits(self, project_id: str, mr_iid: int) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}/commits",
                headers=self.headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_merge_request_note(
        self, project_id: str, mr_iid: int, body: str
    ) -> Dict[str, Any]:
        """Post a general comment on a MR."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}/notes",
                headers=self.headers,
                json={"body": body},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_merge_request_discussion(
        self,
        project_id: str,
        mr_iid: int,
        body: str,
        position: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Post a line-level review comment on a MR."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_base}/projects/{project_id}/merge_requests/{mr_iid}/discussions",
                headers=self.headers,
                json={"body": body, "position": position},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_webhook(
        self,
        project_id: str,
        webhook_url: str,
        token: str,
    ) -> Dict[str, Any]:
        """Register a project webhook."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_base}/projects/{project_id}/hooks",
                headers=self.headers,
                json={
                    "url": webhook_url,
                    "token": token,
                    "merge_requests_events": True,
                    "note_events": True,
                    "push_events": False,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_webhook(self, project_id: str, hook_id: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.api_base}/projects/{project_id}/hooks/{hook_id}",
                headers=self.headers,
            )
            resp.raise_for_status()


def get_oauth_url(state: str) -> str:
    """Build GitLab OAuth authorization URL."""
    base = settings.gitlab_base_url.rstrip("/")
    params = {
        "client_id": settings.gitlab_client_id,
        "redirect_uri": settings.gitlab_redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": "api read_user",
    }
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base}{GITLAB_OAUTH_URL}?{param_str}"


async def exchange_code_for_token(code: str) -> Dict[str, Any]:
    """Exchange OAuth code for access token."""
    base = settings.gitlab_base_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base}{GITLAB_TOKEN_URL}",
            json={
                "client_id": settings.gitlab_client_id,
                "client_secret": settings.gitlab_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.gitlab_redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


def verify_webhook_token(token: str) -> bool:
    """Verify GitLab webhook token."""
    return hmac.compare_digest(token, settings.webhook_secret)
