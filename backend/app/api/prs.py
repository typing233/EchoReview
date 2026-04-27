"""
PR and review session endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.database import get_db
from app.models import User, Repository, PullRequest, ReviewComment, AIReviewSession
from app.schemas import PullRequestOut, ReviewCommentOut, AIReviewSessionOut
from app.auth import get_current_user, get_oauth_token
from app.services.review import trigger_review_for_pr
from app.services.github import GitHubClient
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/prs", tags=["prs"])


@router.get("/{repo_id}")
async def list_pull_requests(
    repo_id: int,
    quality_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List PRs for a repository."""
    repo = await _check_repo_access(repo_id, current_user, db)

    query = select(PullRequest).where(PullRequest.repository_id == repo.id)
    if quality_only:
        query = query.where(PullRequest.is_quality_pr == True)
    query = query.order_by(desc(PullRequest.platform_created_at)).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    prs = result.scalars().all()
    return [PullRequestOut.model_validate(pr) for pr in prs]


@router.get("/{repo_id}/{pr_number}")
async def get_pull_request(
    repo_id: int,
    pr_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific PR with its review comments."""
    repo = await _check_repo_access(repo_id, current_user, db)
    result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.repository_id == repo.id,
                PullRequest.platform_pr_number == pr_number,
            )
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")

    # Get review comments
    comments_result = await db.execute(
        select(ReviewComment)
        .where(ReviewComment.pull_request_id == pr.id)
        .order_by(ReviewComment.platform_created_at)
    )
    comments = comments_result.scalars().all()

    pr_out = PullRequestOut.model_validate(pr)
    return {
        **pr_out.model_dump(),
        "review_comments": [ReviewCommentOut.model_validate(c) for c in comments],
        "diff_preview": (pr.diff_content or "")[:5000],
    }


@router.post("/{repo_id}/{pr_number}/review")
async def trigger_manual_review(
    repo_id: int,
    pr_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger AI review for a specific PR."""
    repo = await _check_repo_access(repo_id, current_user, db)
    access_token = await get_oauth_token(current_user, repo.platform.value, db)
    if not access_token:
        raise HTTPException(status_code=401, detail=f"No {repo.platform.value} account connected")

    result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.repository_id == repo.id,
                PullRequest.platform_pr_number == pr_number,
            )
        )
    )
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")

    from app.models import AIReviewSession, ReviewStatus
    session = AIReviewSession(
        pull_request_id=pr.id,
        status=ReviewStatus.PENDING,
        triggered_by="manual",
    )
    db.add(session)
    await db.commit()

    from app.services.review import run_ai_review
    await run_ai_review(db, session, pr, repo, access_token)
    await db.refresh(session)
    return AIReviewSessionOut.model_validate(session)


@router.get("/{repo_id}/{pr_number}/reviews")
async def list_review_sessions(
    repo_id: int,
    pr_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List AI review sessions for a PR."""
    repo = await _check_repo_access(repo_id, current_user, db)
    pr_result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.repository_id == repo.id,
                PullRequest.platform_pr_number == pr_number,
            )
        )
    )
    pr = pr_result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")

    sessions_result = await db.execute(
        select(AIReviewSession)
        .where(AIReviewSession.pull_request_id == pr.id)
        .order_by(desc(AIReviewSession.created_at))
    )
    sessions = sessions_result.scalars().all()
    return [AIReviewSessionOut.model_validate(s) for s in sessions]


async def _check_repo_access(repo_id: int, user: User, db: AsyncSession) -> Repository:
    result = await db.execute(
        select(Repository).where(
            and_(Repository.id == repo_id, Repository.owner_id == user.id)
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo
