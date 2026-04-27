"""
AI review generation service: generates line-level review comments
by leveraging team knowledge base and similar historical PRs.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from app.models import (
    Platform, ReviewStatus, PullRequest, ReviewComment, Repository,
    KnowledgeItem, AIReviewSession, OAuthAccount,
)
from app.services.github import GitHubClient
from app.services.gitlab import GitLabClient
from app.services import llm as llm_service
import structlog

logger = structlog.get_logger()


async def _get_similar_prs(
    db: AsyncSession,
    repository_id: int,
    diff_content: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Find similar historical PRs using keyword overlap and quality score."""
    result = await db.execute(
        select(PullRequest)
        .where(
            and_(
                PullRequest.repository_id == repository_id,
                PullRequest.is_quality_pr == True,
                PullRequest.diff_content.isnot(None),
            )
        )
        .order_by(desc(PullRequest.quality_score))
        .limit(50)
    )
    prs = result.scalars().all()

    if not prs:
        return []

    # Simple keyword matching heuristic
    import re
    diff_keywords = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', diff_content[:3000]))

    scored = []
    for pr in prs:
        if not pr.diff_content:
            continue
        pr_keywords = set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', pr.diff_content[:3000]))
        overlap = len(diff_keywords & pr_keywords)
        scored.append((overlap, pr))

    scored.sort(reverse=True)
    similar = []
    for _, pr in scored[:limit]:
        # Get key discussion points
        comments_result = await db.execute(
            select(ReviewComment)
            .where(ReviewComment.pull_request_id == pr.id)
            .order_by(desc(ReviewComment.platform_created_at))
            .limit(5)
        )
        comments = comments_result.scalars().all()
        key_discussion = "; ".join(c.body[:100] for c in comments)
        similar.append({
            "id": pr.id,
            "number": pr.platform_pr_number,
            "title": pr.title,
            "pr_url": pr.pr_url,
            "key_discussion": key_discussion,
        })
    return similar


async def _get_relevant_knowledge(
    db: AsyncSession,
    repository_id: int,
    diff_content: str,
    files_changed: List[Dict],
) -> List[Dict[str, Any]]:
    """Find relevant knowledge items for a PR."""
    result = await db.execute(
        select(KnowledgeItem)
        .where(KnowledgeItem.repository_id == repository_id)
        .order_by(desc(KnowledgeItem.confidence_score * KnowledgeItem.occurrence_count))
        .limit(50)
    )
    all_knowledge = result.scalars().all()

    if not all_knowledge:
        return []

    # Filter by file pattern match
    file_names = [f.get("filename", "") for f in files_changed]
    relevant = []
    for item in all_knowledge:
        if not item.file_patterns:
            relevant.append(item)
            continue
        for pattern in item.file_patterns:
            import fnmatch
            if any(fnmatch.fnmatch(f, pattern) for f in file_names):
                relevant.append(item)
                break

    # Use LLM to select most relevant
    knowledge_dicts = [
        {
            "id": item.id,
            "knowledge_type": item.knowledge_type.value,
            "title": item.title,
            "content": item.content,
            "examples": item.examples,
        }
        for item in relevant[:30]
    ]

    selected = await llm_service.find_similar_knowledge(diff_content, knowledge_dicts, top_k=10)
    return selected


async def run_ai_review(
    db: AsyncSession,
    session: AIReviewSession,
    pr: PullRequest,
    repository: Repository,
    access_token: str,
) -> None:
    """
    Execute the full AI review pipeline:
    1. Gather context (knowledge, similar PRs)
    2. Generate review comments via LLM
    3. Post comments to GitHub/GitLab
    """
    try:
        session.status = ReviewStatus.IN_PROGRESS
        await db.commit()

        # Get relevant knowledge items
        knowledge_items = await _get_relevant_knowledge(
            db,
            repository.id,
            pr.diff_content or "",
            pr.files_changed or [],
        )

        # Find similar PRs
        similar_prs = await _get_similar_prs(db, repository.id, pr.diff_content or "")

        # Generate AI review
        review_result = await llm_service.generate_pr_review(
            pr_title=pr.title,
            pr_description=pr.description or "",
            diff_content=pr.diff_content or "",
            changed_files=pr.files_changed or [],
            knowledge_items=knowledge_items,
            similar_prs=similar_prs,
        )

        # Format comments for storage
        ai_comments = review_result.get("comments", [])

        # Enrich comments with knowledge IDs and similar PR refs
        for comment in ai_comments:
            comment.setdefault("related_knowledge_ids", [])
            comment.setdefault("similar_pr_numbers", [])

        session.ai_comments = ai_comments
        session.summary = review_result.get("summary", "")
        session.overall_assessment = review_result.get("overall_assessment", "")
        session.knowledge_items_used = [{"id": k.get("id"), "title": k.get("title")} for k in knowledge_items]
        session.similar_prs = similar_prs

        # Post to platform
        posted = False
        try:
            if repository.platform == Platform.GITHUB:
                posted = await _post_github_review(
                    pr=pr,
                    repository=repository,
                    review_result=review_result,
                    access_token=access_token,
                )
            elif repository.platform == Platform.GITLAB:
                posted = await _post_gitlab_review(
                    pr=pr,
                    repository=repository,
                    review_result=review_result,
                    access_token=access_token,
                )
        except Exception as e:
            logger.error("review_post_failed", error=str(e), pr_id=pr.id)

        session.posted_to_platform = posted
        session.status = ReviewStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("review_completed", session_id=session.id, pr_id=pr.id, comments=len(ai_comments))

    except Exception as e:
        logger.error("review_failed", error=str(e), session_id=session.id)
        session.status = ReviewStatus.FAILED
        session.error_message = str(e)
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def _post_github_review(
    pr: PullRequest,
    repository: Repository,
    review_result: Dict[str, Any],
    access_token: str,
) -> bool:
    """Post AI review comments to GitHub."""
    client = GitHubClient(access_token)
    owner, repo_name = repository.full_name.split("/", 1)
    commit_id = pr.head_sha
    if not commit_id:
        return False

    # Build GitHub review comments format
    comments = []
    for c in review_result.get("comments", []):
        if not c.get("file_path") or not c.get("line_number"):
            continue
        body_parts = [c.get("body", "")]
        if c.get("context_explanation"):
            body_parts.append(f"\n\n> **Context**: {c['context_explanation']}")
        if c.get("suggested_fix"):
            body_parts.append(f"\n\n**Suggested fix:**\n```\n{c['suggested_fix']}\n```")
        severity_emoji = {"error": "🔴", "warning": "🟡", "suggestion": "💡", "info": "ℹ️"}.get(
            c.get("severity", "suggestion"), "💡"
        )
        body = f"{severity_emoji} **[{c.get('category', 'general').upper()}]** {''.join(body_parts)}"
        comments.append({
            "path": c["file_path"],
            "line": c["line_number"],
            "side": "RIGHT",
            "body": body,
        })

    # Build summary body
    assessment_emoji = {"LGTM": "✅", "NEEDS_CHANGES": "❌", "APPROVE_WITH_SUGGESTIONS": "⚠️"}.get(
        review_result.get("overall_assessment", "NEEDS_CHANGES"), "🤖"
    )
    summary_body = f"## 🤖 EchoReview AI Analysis\n\n{assessment_emoji} **{review_result.get('overall_assessment', '')}**\n\n{review_result.get('summary', '')}"

    if review_result.get("key_concerns"):
        summary_body += "\n\n**Key Concerns:**\n" + "\n".join(f"- {c}" for c in review_result["key_concerns"])
    if review_result.get("positive_aspects"):
        summary_body += "\n\n**Positive Aspects:**\n" + "\n".join(f"- {p}" for p in review_result["positive_aspects"])

    await client.create_review(
        owner=owner,
        repo=repo_name,
        pr_number=pr.platform_pr_number,
        commit_id=commit_id,
        body=summary_body,
        comments=comments,
        event="COMMENT",
    )
    return True


async def _post_gitlab_review(
    pr: PullRequest,
    repository: Repository,
    review_result: Dict[str, Any],
    access_token: str,
) -> bool:
    """Post AI review comments to GitLab."""
    client = GitLabClient(access_token)
    project_id = repository.platform_repo_id
    mr_iid = pr.platform_pr_number
    head_sha = pr.head_sha
    base_sha = pr.base_sha

    # Post overall summary as a general note
    assessment_emoji = {"LGTM": "✅", "NEEDS_CHANGES": "❌", "APPROVE_WITH_SUGGESTIONS": "⚠️"}.get(
        review_result.get("overall_assessment", "NEEDS_CHANGES"), "🤖"
    )
    summary_body = f"## 🤖 EchoReview AI Analysis\n\n{assessment_emoji} **{review_result.get('overall_assessment', '')}**\n\n{review_result.get('summary', '')}"
    if review_result.get("key_concerns"):
        summary_body += "\n\n**Key Concerns:**\n" + "\n".join(f"- {c}" for c in review_result["key_concerns"])

    await client.create_merge_request_note(project_id, mr_iid, summary_body)

    # Post line-level comments as discussions
    for c in review_result.get("comments", []):
        if not c.get("file_path") or not c.get("line_number"):
            continue
        body_parts = [c.get("body", "")]
        if c.get("context_explanation"):
            body_parts.append(f"\n\n> **Context**: {c['context_explanation']}")
        if c.get("suggested_fix"):
            body_parts.append(f"\n\n**Suggested fix:**\n```\n{c['suggested_fix']}\n```")
        severity_emoji = {"error": "🔴", "warning": "🟡", "suggestion": "💡", "info": "ℹ️"}.get(
            c.get("severity", "suggestion"), "💡"
        )
        body = f"{severity_emoji} **[{c.get('category', 'general').upper()}]** {''.join(body_parts)}"
        try:
            position = {
                "base_sha": base_sha or "",
                "start_sha": base_sha or "",
                "head_sha": head_sha or "",
                "position_type": "text",
                "new_path": c["file_path"],
                "new_line": c["line_number"],
            }
            await client.create_merge_request_discussion(project_id, mr_iid, body, position)
        except Exception as e:
            logger.warning("gitlab_comment_post_failed", error=str(e), file=c.get("file_path"))

    return True


async def trigger_review_for_pr(
    db: AsyncSession,
    repository: Repository,
    pr_number: int,
    head_sha: str,
    diff_content: str,
    files_changed: List[Dict],
    access_token: str,
    triggered_by: str = "webhook",
) -> AIReviewSession:
    """
    Create or update a PullRequest record and trigger AI review.
    Called from webhook handler.
    """
    from sqlalchemy import select

    # Find or create PR record
    result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.repository_id == repository.id,
                PullRequest.platform_pr_number == pr_number,
            )
        )
    )
    pr = result.scalar_one_or_none()

    if pr:
        # Update with latest diff
        pr.diff_content = diff_content[:50000] if diff_content else pr.diff_content
        pr.head_sha = head_sha
        pr.files_changed = files_changed
    # If no PR found, it will be handled by the webhook collector

    await db.commit()

    if not pr:
        logger.warning("pr_not_found_for_review", pr_number=pr_number, repo_id=repository.id)
        return None

    # Create review session
    session = AIReviewSession(
        pull_request_id=pr.id,
        status=ReviewStatus.PENDING,
        triggered_by=triggered_by,
    )
    db.add(session)
    await db.commit()

    # Run review (in production this would be a Celery task)
    await run_ai_review(db, session, pr, repository, access_token)

    return session
