"""
PR collection service: pulls PR data from GitHub/GitLab and stores it
with structured parsing of diffs, review comments, and adoption tracking.
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models import (
    Platform, PRStatus, PullRequest, ReviewComment, Repository, KnowledgeItem,
    KnowledgeType,
)
from app.services.github import GitHubClient
from app.services.gitlab import GitLabClient
from app.config import settings
from app.services import llm as llm_service
import structlog

logger = structlog.get_logger()


def _compute_quality_score(
    review_count: int,
    comment_count: int,
    additions: int,
    deletions: int,
    has_diff: bool,
) -> float:
    """Heuristic quality score for a PR (0-1)."""
    score = 0.0
    # More review comments → more interesting review data
    score += min(comment_count / 10.0, 0.5)
    # Multiple reviews suggest real review activity
    score += min(review_count / 3.0, 0.3)
    # Non-trivial size
    total_changes = additions + deletions
    if 10 <= total_changes <= 500:
        score += 0.2
    elif total_changes > 500:
        score += 0.1
    return min(score, 1.0)


def _extract_context_from_hunk(diff_hunk: str, body: str) -> Tuple[str, str]:
    """Extract the code context around a review comment from its diff hunk."""
    if not diff_hunk:
        return "", ""
    lines = diff_hunk.split("\n")
    # Split hunk into context-before and context-after the comment location
    # The last modified line is where the comment applies
    before_lines = []
    after_lines = []
    found_comment_line = False
    for line in lines:
        if line.startswith("@@"):
            continue
        if not found_comment_line:
            before_lines.append(line)
        else:
            after_lines.append(line)
    # Return last 5 lines of before, first 3 of after
    return "\n".join(before_lines[-5:]), "\n".join(after_lines[:3])


async def _check_comment_addressed(
    comment: Dict[str, Any],
    commits_after_comment: List[Dict[str, Any]],
    github_client: Optional[GitHubClient],
    gitlab_client: Optional[GitLabClient],
    owner: str,
    repo_name: str,
    project_id: str,
) -> Tuple[Optional[bool], Optional[str], Optional[str]]:
    """
    Check if a review comment was addressed in a subsequent commit.
    Returns (is_addressed, addressing_commit_sha, addressing_diff).
    """
    if not commits_after_comment:
        return None, None, None

    comment_body_keywords = set(
        re.findall(r'\b\w{4,}\b', (comment.get("body") or "").lower())
    ) - {"this", "that", "with", "from", "have", "should", "would", "could"}

    file_path = comment.get("file_path") or comment.get("path") or ""

    for commit in commits_after_comment[:5]:  # check up to 5 commits
        sha = commit.get("sha") or commit.get("id")
        if not sha:
            continue
        try:
            if github_client:
                diff_text = await github_client.get_commit_diff(owner, repo_name, sha)
            else:
                continue
            # Check if the commit touches the same file
            if file_path and file_path not in diff_text:
                continue
            # Heuristic: commit diff shares keywords with comment
            diff_keywords = set(re.findall(r'\b\w{4,}\b', diff_text.lower()))
            overlap = comment_body_keywords & diff_keywords
            if len(overlap) >= 2:
                return True, sha, diff_text[:500]
        except Exception:
            pass
    return False, None, None


async def collect_github_prs(
    db: AsyncSession,
    repository: Repository,
    access_token: str,
    days: int = 90,
    min_review_comments: int = 2,
    max_prs: int = 200,
) -> Dict[str, int]:
    """
    Collect merged PRs from GitHub for a repository,
    parse their diffs, review comments, and adoption tracking.
    """
    client = GitHubClient(access_token)
    owner, repo_name = repository.full_name.split("/", 1)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    stats = {"collected": 0, "skipped": 0, "errors": 0, "knowledge_extracted": 0}

    page = 1
    total_processed = 0

    while total_processed < max_prs:
        try:
            prs = await client.get_pull_requests(owner, repo_name, state="closed", page=page, per_page=50)
        except Exception as e:
            logger.error("github_pr_fetch_failed", error=str(e), page=page)
            break

        if not prs:
            break

        for pr_data in prs:
            if total_processed >= max_prs:
                break

            # Skip if too old
            updated_at_str = pr_data.get("updated_at", "")
            if updated_at_str:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at < cutoff_date:
                    # PRs are sorted by updated desc, so we can stop
                    total_processed = max_prs
                    break

            # Only collect merged PRs (highest quality data)
            if not pr_data.get("merged_at"):
                stats["skipped"] += 1
                continue

            total_processed += 1

            # Check if already collected
            pr_number = pr_data["number"]
            existing = await db.execute(
                select(PullRequest).where(
                    and_(
                        PullRequest.repository_id == repository.id,
                        PullRequest.platform_pr_number == pr_number,
                    )
                )
            )
            if existing.scalar_one_or_none():
                stats["skipped"] += 1
                continue

            try:
                # Get detailed PR data
                pr_detail = await client.get_pull_request(owner, repo_name, pr_number)
                review_comments_raw = await client.get_review_comments(owner, repo_name, pr_number)
                issue_comments_raw = await client.get_issue_comments(owner, repo_name, pr_number)
                reviews_raw = await client.get_pr_reviews(owner, repo_name, pr_number)

                # Filter by min comment count
                total_comments = len(review_comments_raw) + len(issue_comments_raw)
                if total_comments < min_review_comments:
                    stats["skipped"] += 1
                    continue

                # Get diff
                try:
                    diff_content = await client.get_pull_request_diff(owner, repo_name, pr_number)
                except Exception:
                    diff_content = ""

                # Get changed files
                try:
                    files_data = await client.get_pull_request_files(owner, repo_name, pr_number)
                except Exception:
                    files_data = []

                # Get commits for adoption tracking
                try:
                    commits = await client.get_pr_commits(owner, repo_name, pr_number)
                except Exception:
                    commits = []

                # Compute quality score
                quality_score = _compute_quality_score(
                    review_count=len(reviews_raw),
                    comment_count=total_comments,
                    additions=pr_detail.get("additions", 0),
                    deletions=pr_detail.get("deletions", 0),
                    has_diff=bool(diff_content),
                )
                is_quality = quality_score >= 0.3 and total_comments >= min_review_comments

                # Parse dates
                def parse_dt(s):
                    if not s:
                        return None
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))

                # Create PR record
                pr = PullRequest(
                    repository_id=repository.id,
                    platform_pr_number=pr_number,
                    platform_pr_id=str(pr_detail.get("id", pr_number)),
                    title=pr_detail.get("title", ""),
                    description=pr_detail.get("body", "")[:5000] if pr_detail.get("body") else None,
                    author=pr_detail.get("user", {}).get("login", "unknown"),
                    status=PRStatus.MERGED,
                    base_branch=pr_detail.get("base", {}).get("ref", "main"),
                    head_branch=pr_detail.get("head", {}).get("ref", ""),
                    base_sha=pr_detail.get("base", {}).get("sha"),
                    head_sha=pr_detail.get("head", {}).get("sha"),
                    diff_content=diff_content[:settings.pr_max_diff_chars] if diff_content else None,
                    files_changed=[
                        {"filename": f.get("filename"), "additions": f.get("additions", 0),
                         "deletions": f.get("deletions", 0), "status": f.get("status", "")}
                        for f in files_data[:100]
                    ],
                    additions=pr_detail.get("additions", 0),
                    deletions=pr_detail.get("deletions", 0),
                    review_count=len(reviews_raw),
                    comment_count=total_comments,
                    quality_score=quality_score,
                    is_quality_pr=is_quality,
                    pr_url=pr_detail.get("html_url", ""),
                    merged_at=parse_dt(pr_detail.get("merged_at")),
                    platform_created_at=parse_dt(pr_detail.get("created_at")),
                )
                db.add(pr)
                await db.flush()  # get pr.id

                # Process review comments (line-level)
                comment_records = []
                for rc in review_comments_raw:
                    created_at = parse_dt(rc.get("created_at"))
                    # For adoption tracking: find commits after this comment
                    commits_after = [
                        c for c in commits
                        if parse_dt(c.get("commit", {}).get("committer", {}).get("date")) and
                        created_at and
                        parse_dt(c.get("commit", {}).get("committer", {}).get("date")) > created_at
                    ] if created_at else []

                    is_addressed, addr_commit, addr_diff = await _check_comment_addressed(
                        {"body": rc.get("body", ""), "file_path": rc.get("path"), "path": rc.get("path")},
                        commits_after,
                        client,
                        None,
                        owner,
                        repo_name,
                        "",
                    )

                    context_before, context_after = _extract_context_from_hunk(
                        rc.get("diff_hunk", ""),
                        rc.get("body", ""),
                    )

                    comment = ReviewComment(
                        pull_request_id=pr.id,
                        platform_comment_id=str(rc.get("id", "")),
                        author=rc.get("user", {}).get("login", "unknown"),
                        body=rc.get("body", ""),
                        file_path=rc.get("path"),
                        diff_hunk=rc.get("diff_hunk", "")[:2000] if rc.get("diff_hunk") else None,
                        line_number=rc.get("line") or rc.get("original_line"),
                        original_line=rc.get("original_line"),
                        comment_type="line",
                        parent_id=str(rc.get("in_reply_to_id")) if rc.get("in_reply_to_id") else None,
                        is_addressed=is_addressed,
                        addressing_commit=addr_commit,
                        addressing_diff=addr_diff,
                        context_before=context_before,
                        context_after=context_after,
                        platform_created_at=created_at,
                    )
                    comment_records.append(comment)
                    db.add(comment)

                # Process general issue comments
                for ic in issue_comments_raw:
                    comment = ReviewComment(
                        pull_request_id=pr.id,
                        platform_comment_id=f"issue_{ic.get('id', '')}",
                        author=ic.get("user", {}).get("login", "unknown"),
                        body=ic.get("body", ""),
                        comment_type="general",
                        platform_created_at=parse_dt(ic.get("created_at")),
                    )
                    comment_records.append(comment)
                    db.add(comment)

                await db.commit()
                stats["collected"] += 1
                logger.info("pr_collected", pr_number=pr_number, quality=is_quality)

                # Extract knowledge from quality PRs
                if is_quality:
                    try:
                        knowledge_items = await llm_service.extract_knowledge_from_pr(
                            pr_title=pr.title,
                            pr_description=pr.description or "",
                            diff_content=diff_content[:3000],
                            review_comments=[
                                {
                                    "file_path": c.file_path,
                                    "line_number": c.line_number,
                                    "author": c.author,
                                    "body": c.body,
                                    "is_addressed": c.is_addressed,
                                    "addressing_diff": c.addressing_diff,
                                }
                                for c in comment_records[:30]
                            ],
                        )

                        for item_data in knowledge_items:
                            # Generate embedding
                            embed_text = f"{item_data.get('title', '')} {item_data.get('content', '')}"
                            try:
                                embedding = await llm_service.get_embedding(embed_text)
                            except Exception:
                                embedding = None

                            ki = KnowledgeItem(
                                repository_id=repository.id,
                                knowledge_type=KnowledgeType(item_data.get("knowledge_type", "best_practice")),
                                title=item_data.get("title", "")[:1024],
                                content=item_data.get("content", ""),
                                examples=item_data.get("examples"),
                                source_pr_ids=[pr.id],
                                tags=item_data.get("tags"),
                                file_patterns=item_data.get("file_patterns"),
                                confidence_score=float(item_data.get("confidence_score", 0.7)),
                                embedding=embedding,
                            )
                            db.add(ki)

                        await db.commit()
                        stats["knowledge_extracted"] += len(knowledge_items)
                    except Exception as e:
                        logger.error("knowledge_extraction_error", error=str(e), pr_id=pr.id)
                        await db.rollback()

            except Exception as e:
                logger.error("pr_collection_error", error=str(e), pr_number=pr_number)
                await db.rollback()
                stats["errors"] += 1

        page += 1

    # Update last_collected_at
    repository.last_collected_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("collection_complete", stats=stats, repo=repository.full_name)
    return stats


async def collect_gitlab_mrs(
    db: AsyncSession,
    repository: Repository,
    access_token: str,
    days: int = 90,
    min_review_comments: int = 2,
    max_prs: int = 200,
) -> Dict[str, int]:
    """
    Collect merged MRs from GitLab for a repository.
    """
    client = GitLabClient(access_token)
    project_id = repository.platform_repo_id
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    stats = {"collected": 0, "skipped": 0, "errors": 0, "knowledge_extracted": 0}

    page = 1
    total_processed = 0

    while total_processed < max_prs:
        try:
            mrs = await client.get_merge_requests(project_id, state="merged", page=page, per_page=50)
        except Exception as e:
            logger.error("gitlab_mr_fetch_failed", error=str(e))
            break

        if not mrs:
            break

        for mr_data in mrs:
            if total_processed >= max_prs:
                break

            updated_at_str = mr_data.get("updated_at", "")
            if updated_at_str:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at < cutoff_date:
                    total_processed = max_prs
                    break

            total_processed += 1

            mr_iid = mr_data["iid"]

            # Check if already collected
            existing = await db.execute(
                select(PullRequest).where(
                    and_(
                        PullRequest.repository_id == repository.id,
                        PullRequest.platform_pr_number == mr_iid,
                    )
                )
            )
            if existing.scalar_one_or_none():
                stats["skipped"] += 1
                continue

            try:
                discussions = await client.get_merge_request_discussions(project_id, mr_iid)
                changes_data = await client.get_merge_request_changes(project_id, mr_iid)

                # Count review-relevant discussions (not system notes)
                review_discussions = [
                    d for d in discussions
                    if d.get("notes") and not d["notes"][0].get("system", False)
                    and d["notes"][0].get("type") in ("DiffNote", None)
                ]

                total_comments = sum(len(d.get("notes", [])) for d in review_discussions)
                if total_comments < min_review_comments:
                    stats["skipped"] += 1
                    continue

                # Build diff from changes
                changes = changes_data.get("changes", [])
                diff_parts = []
                for change in changes[:50]:
                    diff_parts.append(f"--- a/{change.get('old_path', '')}")
                    diff_parts.append(f"+++ b/{change.get('new_path', '')}")
                    diff_parts.append(change.get("diff", "")[:1000])
                diff_content = "\n".join(diff_parts)

                def parse_dt(s):
                    if not s:
                        return None
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))

                quality_score = _compute_quality_score(
                    review_count=len(review_discussions),
                    comment_count=total_comments,
                    additions=mr_data.get("changes_count", 0) or 0,
                    deletions=0,
                    has_diff=bool(diff_content),
                )
                is_quality = quality_score >= 0.3

                pr = PullRequest(
                    repository_id=repository.id,
                    platform_pr_number=mr_iid,
                    platform_pr_id=str(mr_data.get("id", mr_iid)),
                    title=mr_data.get("title", ""),
                    description=mr_data.get("description", "")[:5000] if mr_data.get("description") else None,
                    author=mr_data.get("author", {}).get("username", "unknown"),
                    status=PRStatus.MERGED,
                    base_branch=mr_data.get("target_branch", "main"),
                    head_branch=mr_data.get("source_branch", ""),
                    diff_content=diff_content[:settings.pr_max_diff_chars],
                    files_changed=[
                        {"filename": c.get("new_path", c.get("old_path", "")),
                         "additions": 0, "deletions": 0, "status": "modified"}
                        for c in changes[:100]
                    ],
                    additions=0,
                    deletions=0,
                    review_count=len(review_discussions),
                    comment_count=total_comments,
                    quality_score=quality_score,
                    is_quality_pr=is_quality,
                    pr_url=mr_data.get("web_url", ""),
                    merged_at=parse_dt(mr_data.get("merged_at")),
                    platform_created_at=parse_dt(mr_data.get("created_at")),
                )
                db.add(pr)
                await db.flush()

                # Process discussions
                comment_records = []
                for discussion in review_discussions:
                    for note in discussion.get("notes", []):
                        position = note.get("position") or {}
                        context_before, context_after = _extract_context_from_hunk(
                            note.get("diff_hunk", ""),
                            note.get("body", ""),
                        )
                        comment = ReviewComment(
                            pull_request_id=pr.id,
                            platform_comment_id=str(note.get("id", "")),
                            author=note.get("author", {}).get("username", "unknown"),
                            body=note.get("body", ""),
                            file_path=position.get("new_path") or position.get("old_path"),
                            line_number=position.get("new_line") or position.get("old_line"),
                            comment_type="line" if position else "general",
                            context_before=context_before,
                            context_after=context_after,
                            platform_created_at=parse_dt(note.get("created_at")),
                        )
                        comment_records.append(comment)
                        db.add(comment)

                await db.commit()
                stats["collected"] += 1

                if is_quality:
                    try:
                        knowledge_items = await llm_service.extract_knowledge_from_pr(
                            pr_title=pr.title,
                            pr_description=pr.description or "",
                            diff_content=diff_content[:3000],
                            review_comments=[
                                {"file_path": c.file_path, "line_number": c.line_number,
                                 "author": c.author, "body": c.body}
                                for c in comment_records[:30]
                            ],
                        )
                        for item_data in knowledge_items:
                            embed_text = f"{item_data.get('title', '')} {item_data.get('content', '')}"
                            try:
                                embedding = await llm_service.get_embedding(embed_text)
                            except Exception:
                                embedding = None
                            ki = KnowledgeItem(
                                repository_id=repository.id,
                                knowledge_type=KnowledgeType(item_data.get("knowledge_type", "best_practice")),
                                title=item_data.get("title", "")[:1024],
                                content=item_data.get("content", ""),
                                examples=item_data.get("examples"),
                                source_pr_ids=[pr.id],
                                tags=item_data.get("tags"),
                                file_patterns=item_data.get("file_patterns"),
                                confidence_score=float(item_data.get("confidence_score", 0.7)),
                                embedding=embedding,
                            )
                            db.add(ki)
                        await db.commit()
                        stats["knowledge_extracted"] += len(knowledge_items)
                    except Exception as e:
                        logger.error("knowledge_extraction_error", error=str(e))
                        await db.rollback()

            except Exception as e:
                logger.error("mr_collection_error", error=str(e), mr_iid=mr_iid)
                await db.rollback()
                stats["errors"] += 1

        page += 1

    repository.last_collected_at = datetime.now(timezone.utc)
    await db.commit()
    return stats
