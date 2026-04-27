"""
Repository management endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.database import get_db
from app.models import User, Repository, PullRequest, Platform, OAuthAccount
from app.schemas import RepositoryOut, RepositoryCreate, RepositoryListItem, CollectionRequest
from app.auth import get_current_user, get_oauth_token
from app.services.github import GitHubClient
from app.services.gitlab import GitLabClient
from app.services.collector import collect_github_prs, collect_gitlab_mrs
from app.config import settings
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.get("/available", response_model=List[RepositoryListItem])
async def list_available_repositories(
    platform: str = Query(..., description="github or gitlab"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List repositories available from GitHub/GitLab for import."""
    access_token = await get_oauth_token(current_user, platform, db)
    if not access_token:
        raise HTTPException(status_code=401, detail=f"No {platform} account connected")

    try:
        if platform == "github":
            client = GitHubClient(access_token)
            repos_raw = await client.get_repositories()
            return [
                RepositoryListItem(
                    platform_repo_id=str(r["id"]),
                    full_name=r["full_name"],
                    name=r["name"],
                    description=r.get("description"),
                    default_branch=r.get("default_branch", "main"),
                    private=r.get("private", False),
                    platform=Platform.GITHUB,
                )
                for r in repos_raw
            ]
        elif platform == "gitlab":
            client = GitLabClient(access_token)
            repos_raw = await client.get_repositories()
            return [
                RepositoryListItem(
                    platform_repo_id=str(r["id"]),
                    full_name=r["path_with_namespace"],
                    name=r["name"],
                    description=r.get("description"),
                    default_branch=r.get("default_branch", "main"),
                    private=r.get("visibility") == "private",
                    platform=Platform.GITLAB,
                )
                for r in repos_raw
            ]
        else:
            raise HTTPException(status_code=400, detail="Invalid platform")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch repositories: {e}")


@router.post("", response_model=RepositoryOut, status_code=201)
async def add_repository(
    payload: RepositoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a repository to EchoReview for monitoring."""
    # Check if already added
    result = await db.execute(
        select(Repository).where(
            and_(
                Repository.platform == payload.platform,
                Repository.platform_repo_id == payload.platform_repo_id,
                Repository.owner_id == current_user.id,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return _repo_out(existing)

    repo = Repository(
        owner_id=current_user.id,
        platform=payload.platform,
        platform_repo_id=payload.platform_repo_id,
        full_name=payload.full_name,
        name=payload.name,
        description=payload.description,
        default_branch=payload.default_branch,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return _repo_out(repo)


@router.get("", response_model=List[RepositoryOut])
async def list_repositories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List repositories added by current user."""
    result = await db.execute(
        select(Repository).where(Repository.owner_id == current_user.id)
    )
    repos = result.scalars().all()
    out = []
    for repo in repos:
        ro = _repo_out(repo)
        # Add counts
        pr_count_result = await db.execute(
            select(func.count(PullRequest.id)).where(PullRequest.repository_id == repo.id)
        )
        ro.pr_count = pr_count_result.scalar()
        quality_count_result = await db.execute(
            select(func.count(PullRequest.id)).where(
                and_(PullRequest.repository_id == repo.id, PullRequest.is_quality_pr == True)
            )
        )
        ro.quality_pr_count = quality_count_result.scalar()
        out.append(ro)
    return out


@router.get("/{repo_id}", response_model=RepositoryOut)
async def get_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await _get_repo(repo_id, current_user, db)
    return _repo_out(repo)


@router.delete("/{repo_id}", status_code=204)
async def delete_repository(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repo = await _get_repo(repo_id, current_user, db)
    # Remove webhook if active
    if repo.webhook_active and repo.webhook_id:
        access_token = await get_oauth_token(current_user, repo.platform.value, db)
        if access_token:
            try:
                if repo.platform == Platform.GITHUB:
                    owner, repo_name = repo.full_name.split("/", 1)
                    client = GitHubClient(access_token)
                    await client.delete_webhook(owner, repo_name, repo.webhook_id)
                elif repo.platform == Platform.GITLAB:
                    client = GitLabClient(access_token)
                    await client.delete_webhook(repo.platform_repo_id, repo.webhook_id)
            except Exception as e:
                logger.warning("webhook_deletion_failed", error=str(e))
    await db.delete(repo)
    await db.commit()


@router.post("/{repo_id}/collect")
async def trigger_collection(
    repo_id: int,
    request: CollectionRequest = CollectionRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger PR/MR collection for a repository.
    Pulls quality PRs from the past N days and extracts knowledge.
    """
    repo = await _get_repo(repo_id, current_user, db)
    access_token = await get_oauth_token(current_user, repo.platform.value, db)
    if not access_token:
        raise HTTPException(status_code=401, detail=f"No {repo.platform.value} account connected")

    async def _do_collect():
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Repository).where(Repository.id == repo_id))
            repo_fresh = result.scalar_one_or_none()
            if not repo_fresh:
                return
            if repo_fresh.platform == Platform.GITHUB:
                stats = await collect_github_prs(
                    session, repo_fresh, access_token,
                    days=request.days,
                    min_review_comments=request.min_review_comments,
                    max_prs=request.max_prs,
                )
            else:
                stats = await collect_gitlab_mrs(
                    session, repo_fresh, access_token,
                    days=request.days,
                    min_review_comments=request.min_review_comments,
                    max_prs=request.max_prs,
                )
            logger.info("collection_done", repo_id=repo_id, stats=stats)

    background_tasks.add_task(_do_collect)
    return {"message": "Collection started", "repository_id": repo_id}


@router.post("/{repo_id}/webhook")
async def setup_webhook(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a webhook on GitHub/GitLab for auto-review on new PRs."""
    repo = await _get_repo(repo_id, current_user, db)
    access_token = await get_oauth_token(current_user, repo.platform.value, db)
    if not access_token:
        raise HTTPException(status_code=401, detail=f"No {repo.platform.value} account connected")

    webhook_url = f"{settings.backend_url}/api/webhooks/{repo.platform.value}"

    try:
        if repo.platform == Platform.GITHUB:
            owner, repo_name = repo.full_name.split("/", 1)
            client = GitHubClient(access_token)
            hook_data = await client.create_webhook(owner, repo_name, webhook_url, settings.webhook_secret)
            repo.webhook_id = str(hook_data["id"])
        elif repo.platform == Platform.GITLAB:
            client = GitLabClient(access_token)
            hook_data = await client.create_webhook(repo.platform_repo_id, webhook_url, settings.webhook_secret)
            repo.webhook_id = str(hook_data["id"])

        repo.webhook_active = True
        await db.commit()
        return {"message": "Webhook registered", "webhook_id": repo.webhook_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook registration failed: {e}")


@router.delete("/{repo_id}/webhook", status_code=204)
async def remove_webhook(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the webhook from GitHub/GitLab."""
    repo = await _get_repo(repo_id, current_user, db)
    if not repo.webhook_active or not repo.webhook_id:
        raise HTTPException(status_code=404, detail="No active webhook")
    access_token = await get_oauth_token(current_user, repo.platform.value, db)
    if not access_token:
        raise HTTPException(status_code=401, detail="No platform account connected")

    try:
        if repo.platform == Platform.GITHUB:
            owner, repo_name = repo.full_name.split("/", 1)
            client = GitHubClient(access_token)
            await client.delete_webhook(owner, repo_name, repo.webhook_id)
        elif repo.platform == Platform.GITLAB:
            client = GitLabClient(access_token)
            await client.delete_webhook(repo.platform_repo_id, repo.webhook_id)
    except Exception as e:
        logger.warning("webhook_removal_failed", error=str(e))

    repo.webhook_active = False
    repo.webhook_id = None
    await db.commit()


async def _get_repo(repo_id: int, user: User, db: AsyncSession) -> Repository:
    result = await db.execute(
        select(Repository).where(
            and_(Repository.id == repo_id, Repository.owner_id == user.id)
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def _repo_out(repo: Repository) -> RepositoryOut:
    return RepositoryOut(
        id=repo.id,
        platform=repo.platform,
        platform_repo_id=repo.platform_repo_id,
        full_name=repo.full_name,
        name=repo.name,
        description=repo.description,
        default_branch=repo.default_branch,
        webhook_active=repo.webhook_active,
        collection_enabled=repo.collection_enabled,
        last_collected_at=repo.last_collected_at,
        created_at=repo.created_at,
    )
