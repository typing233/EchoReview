"""
Webhook handlers for GitHub and GitLab PR events.
Automatically triggers AI review when PRs are opened/synchronized.
"""
import json
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models import Platform, PRStatus, PullRequest, Repository, OAuthAccount
from app.services.github import verify_webhook_signature, GitHubClient
from app.services.gitlab import verify_webhook_token
from app.config import settings
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub webhook events."""
    body = await request.body()

    # Verify signature
    if not x_hub_signature_256 or not verify_webhook_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body)
    event = x_github_event

    if event not in ("pull_request", "pull_request_review", "pull_request_review_comment"):
        return {"message": "Event ignored"}

    action = payload.get("action", "")
    pr_data = payload.get("pull_request", {})

    # Only act on opened/synchronized/reopened PRs
    if event == "pull_request" and action not in ("opened", "synchronize", "reopened"):
        return {"message": "Action ignored"}

    repo_data = payload.get("repository", {})
    repo_full_name = repo_data.get("full_name", "")
    platform_repo_id = str(repo_data.get("id", ""))

    # Find the repository
    result = await db.execute(
        select(Repository).where(
            and_(
                Repository.platform == Platform.GITHUB,
                Repository.platform_repo_id == platform_repo_id,
            )
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        logger.warning("webhook_repo_not_found", full_name=repo_full_name)
        return {"message": "Repository not tracked"}

    pr_number = pr_data.get("number")
    head_sha = pr_data.get("head", {}).get("sha", "")
    head_branch = pr_data.get("head", {}).get("ref", "")
    base_branch = pr_data.get("base", {}).get("ref", "main")
    base_sha = pr_data.get("base", {}).get("sha", "")

    if not pr_number:
        return {"message": "No PR number"}

    # Get the owner's access token
    account_result = await db.execute(
        select(OAuthAccount).where(
            and_(
                OAuthAccount.user_id == repository.owner_id,
                OAuthAccount.platform == Platform.GITHUB,
            )
        )
    )
    oauth_account = account_result.scalar_one_or_none()
    if not oauth_account:
        logger.warning("no_oauth_token", repo_id=repository.id)
        return {"message": "No OAuth token"}

    access_token = oauth_account.access_token

    async def _handle_pr_review():
        from app.database import AsyncSessionLocal
        from app.models import PRStatus
        async with AsyncSessionLocal() as session:
            # Fetch diff and files
            try:
                client = GitHubClient(access_token)
                diff_content = await client.get_pull_request_diff(
                    *repo_full_name.split("/", 1), pr_number
                )
                files_data = await client.get_pull_request_files(
                    *repo_full_name.split("/", 1), pr_number
                )
                pr_detail = await client.get_pull_request(
                    *repo_full_name.split("/", 1), pr_number
                )
            except Exception as e:
                logger.error("webhook_fetch_failed", error=str(e))
                return

            # Upsert PR record
            from sqlalchemy import select, and_
            result = await session.execute(
                select(PullRequest).where(
                    and_(
                        PullRequest.repository_id == repository.id,
                        PullRequest.platform_pr_number == pr_number,
                    )
                )
            )
            pr = result.scalar_one_or_none()

            from datetime import datetime, timezone
            def parse_dt(s):
                if not s:
                    return None
                return datetime.fromisoformat(s.replace("Z", "+00:00"))

            if not pr:
                pr = PullRequest(
                    repository_id=repository.id,
                    platform_pr_number=pr_number,
                    platform_pr_id=str(pr_detail.get("id", pr_number)),
                    title=pr_detail.get("title", ""),
                    description=(pr_detail.get("body") or "")[:5000],
                    author=pr_detail.get("user", {}).get("login", "unknown"),
                    status=PRStatus.OPEN,
                    base_branch=base_branch,
                    head_branch=head_branch,
                    base_sha=base_sha,
                    head_sha=head_sha,
                    diff_content=diff_content[:50000],
                    files_changed=[
                        {"filename": f.get("filename"), "additions": f.get("additions", 0),
                         "deletions": f.get("deletions", 0)}
                        for f in files_data[:100]
                    ],
                    additions=pr_detail.get("additions", 0),
                    deletions=pr_detail.get("deletions", 0),
                    review_count=0,
                    comment_count=0,
                    pr_url=pr_detail.get("html_url", ""),
                    platform_created_at=parse_dt(pr_detail.get("created_at")),
                )
                session.add(pr)
                await session.flush()
            else:
                pr.diff_content = diff_content[:50000]
                pr.head_sha = head_sha
                pr.files_changed = [
                    {"filename": f.get("filename"), "additions": f.get("additions", 0),
                     "deletions": f.get("deletions", 0)}
                    for f in files_data[:100]
                ]

            await session.commit()

            # Trigger AI review
            from app.models import AIReviewSession, ReviewStatus, Repository as Repo
            repo_result = await session.execute(
                select(Repo).where(Repo.id == repository.id)
            )
            repo_fresh = repo_result.scalar_one()

            review_session = AIReviewSession(
                pull_request_id=pr.id,
                status=ReviewStatus.PENDING,
                triggered_by="webhook",
            )
            session.add(review_session)
            await session.commit()

            from app.services.review import run_ai_review
            await run_ai_review(session, review_session, pr, repo_fresh, access_token)

    background_tasks.add_task(_handle_pr_review)
    return {"message": "Webhook received, review queued", "pr_number": pr_number}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_gitlab_token: str = Header(None),
    x_gitlab_event: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Handle GitLab webhook events."""
    if not x_gitlab_token or not verify_webhook_token(x_gitlab_token):
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    body = await request.body()
    payload = json.loads(body)
    event = x_gitlab_event or payload.get("object_kind", "")

    if event not in ("merge_request",):
        return {"message": "Event ignored"}

    attrs = payload.get("object_attributes", {})
    action = attrs.get("action", "")
    if action not in ("open", "update", "reopen"):
        return {"message": "Action ignored"}

    project = payload.get("project", {})
    platform_repo_id = str(project.get("id", ""))
    mr_iid = attrs.get("iid")
    head_sha = attrs.get("last_commit", {}).get("id", "")
    base_branch = attrs.get("target_branch", "main")
    head_branch = attrs.get("source_branch", "")

    result = await db.execute(
        select(Repository).where(
            and_(
                Repository.platform == Platform.GITLAB,
                Repository.platform_repo_id == platform_repo_id,
            )
        )
    )
    repository = result.scalar_one_or_none()
    if not repository:
        return {"message": "Repository not tracked"}

    account_result = await db.execute(
        select(OAuthAccount).where(
            and_(
                OAuthAccount.user_id == repository.owner_id,
                OAuthAccount.platform == Platform.GITLAB,
            )
        )
    )
    oauth_account = account_result.scalar_one_or_none()
    if not oauth_account:
        return {"message": "No OAuth token"}

    access_token = oauth_account.access_token

    async def _handle_mr_review():
        from app.database import AsyncSessionLocal
        from app.services.gitlab import GitLabClient
        async with AsyncSessionLocal() as session:
            try:
                client = GitLabClient(access_token)
                mr_data = await client.get_merge_request(platform_repo_id, mr_iid)
                changes_data = await client.get_merge_request_changes(platform_repo_id, mr_iid)
            except Exception as e:
                logger.error("gitlab_webhook_fetch_failed", error=str(e))
                return

            changes = changes_data.get("changes", [])
            diff_parts = []
            for change in changes[:50]:
                diff_parts.append(f"--- a/{change.get('old_path', '')}")
                diff_parts.append(f"+++ b/{change.get('new_path', '')}")
                diff_parts.append(change.get("diff", "")[:1000])
            diff_content = "\n".join(diff_parts)

            from sqlalchemy import select, and_
            result = await session.execute(
                select(PullRequest).where(
                    and_(
                        PullRequest.repository_id == repository.id,
                        PullRequest.platform_pr_number == mr_iid,
                    )
                )
            )
            pr = result.scalar_one_or_none()

            from datetime import datetime, timezone
            def parse_dt(s):
                if not s: return None
                return datetime.fromisoformat(s.replace("Z", "+00:00"))

            if not pr:
                pr = PullRequest(
                    repository_id=repository.id,
                    platform_pr_number=mr_iid,
                    platform_pr_id=str(mr_data.get("id", mr_iid)),
                    title=mr_data.get("title", ""),
                    description=(mr_data.get("description") or "")[:5000],
                    author=mr_data.get("author", {}).get("username", "unknown"),
                    status=PRStatus.OPEN,
                    base_branch=base_branch,
                    head_branch=head_branch,
                    head_sha=head_sha,
                    diff_content=diff_content[:50000],
                    files_changed=[
                        {"filename": c.get("new_path", c.get("old_path", "")), "additions": 0, "deletions": 0}
                        for c in changes[:100]
                    ],
                    pr_url=mr_data.get("web_url", ""),
                    platform_created_at=parse_dt(mr_data.get("created_at")),
                )
                session.add(pr)
                await session.flush()
            else:
                pr.diff_content = diff_content[:50000]
                pr.head_sha = head_sha

            await session.commit()

            from app.models import AIReviewSession, ReviewStatus, Repository as Repo
            repo_result = await session.execute(select(Repo).where(Repo.id == repository.id))
            repo_fresh = repo_result.scalar_one()

            review_session = AIReviewSession(
                pull_request_id=pr.id,
                status=ReviewStatus.PENDING,
                triggered_by="webhook",
            )
            session.add(review_session)
            await session.commit()

            from app.services.review import run_ai_review
            await run_ai_review(session, review_session, pr, repo_fresh, access_token)

    background_tasks.add_task(_handle_mr_review)
    return {"message": "Webhook received, review queued", "mr_iid": mr_iid}
