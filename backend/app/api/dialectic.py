"""
Dialectic Logic Detection Service.
Detects architectural logic conflicts by cross-validating:
1. Current PR discussion thread and commits
2. Historical dispute records in the knowledge base

This runs during PR processing to catch architectural inconsistencies.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from app.database import get_db
from app.models import (
    User, Repository, KnowledgeItem, KnowledgeType,
    PullRequest, ReviewComment, AIReviewSession,
)
from app.auth import get_current_user
from app.config import settings
import structlog
import json

logger = structlog.get_logger()
router = APIRouter(prefix="/dialectic", tags=["dialectic"])


class LogicConflict(BaseModel):
    conflict_type: str
    severity: str
    title: str
    description: str
    current_pr_context: Dict[str, Any]
    historical_refs: List[Dict[str, Any]]
    suggested_resolution: Optional[str] = None
    confidence_score: float = 0.0


class DialecticCheckResult(BaseModel):
    pr_id: int
    pr_number: int
    status: str
    conflicts: List[LogicConflict]
    summary: str
    overall_risk: str
    check_timestamp: str


class DiscussionThread(BaseModel):
    comment_id: int
    author: str
    body: str
    file_path: Optional[str]
    line_number: Optional[int]
    is_addressed: Optional[bool]
    created_at: Optional[str]


@router.get("/check/{repo_id}/{pr_number}", response_model=DialecticCheckResult)
async def run_dialectic_check(
    repo_id: int,
    pr_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run dialectic logic detection on a PR.
    Extracts discussion thread and commits, then cross-validates with historical_dispute records.
    """
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
    
    discussion_thread = await _extract_discussion_thread(db, pr.id)
    
    historical_disputes = await _get_historical_disputes(db, repo.id)
    
    conflicts = await _detect_logic_conflicts(
        pr=pr,
        discussion=discussion_thread,
        historical_disputes=historical_disputes,
        db=db,
    )
    
    overall_risk = _calculate_overall_risk(conflicts)
    summary = _generate_check_summary(conflicts, overall_risk)
    
    return DialecticCheckResult(
        pr_id=pr.id,
        pr_number=pr.platform_pr_number,
        status="completed",
        conflicts=conflicts,
        summary=summary,
        overall_risk=overall_risk,
        check_timestamp=datetime.utcnow().isoformat(),
    )


async def _extract_discussion_thread(
    db: AsyncSession,
    pr_id: int,
) -> List[DiscussionThread]:
    """Extract all review comments and discussion from a PR."""
    result = await db.execute(
        select(ReviewComment)
        .where(ReviewComment.pull_request_id == pr_id)
        .order_by(ReviewComment.platform_created_at)
    )
    comments = result.scalars().all()
    
    return [
        DiscussionThread(
            comment_id=c.id,
            author=c.author,
            body=c.body,
            file_path=c.file_path,
            line_number=c.line_number,
            is_addressed=c.is_addressed,
            created_at=c.platform_created_at.isoformat() if c.platform_created_at else None,
        )
        for c in comments
    ]


async def _get_historical_disputes(
    db: AsyncSession,
    repo_id: int,
) -> List[Dict[str, Any]]:
    """Get all historical_dispute knowledge items for cross-validation."""
    result = await db.execute(
        select(KnowledgeItem)
        .where(
            and_(
                KnowledgeItem.repository_id == repo_id,
                KnowledgeItem.knowledge_type == KnowledgeType.HISTORICAL_DISPUTE,
            )
        )
        .order_by(desc(KnowledgeItem.confidence_score * KnowledgeItem.occurrence_count))
    )
    items = result.scalars().all()
    
    return [
        {
            "id": item.id,
            "title": item.title,
            "content": item.content,
            "examples": item.examples,
            "tags": item.tags,
            "confidence_score": item.confidence_score,
            "occurrence_count": item.occurrence_count,
            "source_pr_ids": item.source_pr_ids,
        }
        for item in items
    ]


async def _detect_logic_conflicts(
    pr: PullRequest,
    discussion: List[DiscussionThread],
    historical_disputes: List[Dict[str, Any]],
    db: AsyncSession,
) -> List[LogicConflict]:
    """
    Detect logic conflicts by comparing:
    1. Current PR's code changes (diff)
    2. Discussion thread topics
    3. Historical dispute patterns
    
    Types of conflicts detected:
    - architectural_pattern_conflict: Code contradicts established architectural decisions
    - naming_convention_conflict: Naming contradicts team conventions
    - dependency_conflict: Changes contradict dependency management decisions
    - security_pattern_conflict: Security-related patterns contradict past decisions
    """
    conflicts: List[LogicConflict] = []
    
    if not historical_disputes:
        return conflicts
    
    pr_diff = pr.diff_content or ""
    pr_title = pr.title or ""
    pr_description = pr.description or ""
    
    combined_current_text = f"{pr_title}\n{pr_description}\n{pr_diff[:8000]}"
    for comment in discussion:
        combined_current_text += f"\n[Comment by {comment.author}]: {comment.body}"
    
    for dispute in historical_disputes:
        conflict = await _check_dispute_match(
            combined_current_text=combined_current_text,
            dispute=dispute,
            pr=pr,
            discussion=discussion,
        )
        if conflict:
            conflicts.append(conflict)
    
    return conflicts


async def _check_dispute_match(
    combined_current_text: str,
    dispute: Dict[str, Any],
    pr: PullRequest,
    discussion: List[DiscussionThread],
) -> Optional[LogicConflict]:
    """
    Check if current PR matches any historical dispute pattern.
    Uses keyword and semantic matching heuristics.
    """
    import re
    
    dispute_title = dispute.get("title", "").lower()
    dispute_content = dispute.get("content", "").lower()
    dispute_tags = [t.lower() for t in (dispute.get("tags") or [])]
    
    current_lower = combined_current_text.lower()
    
    match_score = 0
    matched_terms = []
    
    tag_keywords = {
        "architecture": ["architecture", "design", "pattern", "layer", "module", "dependency", "coupling", "cohesion"],
        "security": ["security", "auth", "authentication", "authorization", "token", "password", "encrypt", "vulnerability"],
        "naming": ["naming", "convention", "variable", "function", "class", "method", "camel", "snake", "pascal"],
        "performance": ["performance", "speed", "slow", "optimize", "n+1", "query", "cache", "memory"],
        "error": ["error", "exception", "handling", "try", "catch", "throw", "raise", "fail"],
    }
    
    for tag in dispute_tags:
        if tag in tag_keywords:
            for kw in tag_keywords[tag]:
                if kw in current_lower:
                    match_score += 0.3
                    matched_terms.append(kw)
    
    title_words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', dispute_title)
    for word in title_words:
        if word in current_lower and len(word) > 3:
            match_score += 0.2
            matched_terms.append(word)
    
    content_keywords = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{4,}\b', dispute_content)
    for word in set(content_keywords):
        if word in current_lower and current_lower.count(word) >= 2:
            match_score += 0.1
    
    if dispute.get("examples"):
        for example in dispute["examples"]:
            example_lower = str(example).lower()
            example_words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', example_lower)
            overlap = sum(1 for w in example_words if w in current_lower)
            if overlap >= 2:
                match_score += 0.4 * (overlap / len(example_words))
    
    confidence_threshold = 0.5 + (dispute.get("confidence_score", 0.5) * 0.3)
    
    if match_score >= confidence_threshold and len(matched_terms) >= 2:
        conflict_type = _classify_conflict_type(dispute_tags, matched_terms)
        severity = _calculate_severity(match_score, dispute)
        
        return LogicConflict(
            conflict_type=conflict_type,
            severity=severity,
            title=f"Potential conflict: {dispute.get('title')}",
            description=_generate_conflict_description(
                pr=pr,
                dispute=dispute,
                matched_terms=matched_terms,
                discussion=discussion,
            ),
            current_pr_context={
                "pr_number": pr.platform_pr_number,
                "pr_title": pr.title,
                "files_changed": [f.get("filename") for f in (pr.files_changed or [])][:5],
                "matched_terms": list(set(matched_terms))[:10],
            },
            historical_refs=[
                {
                    "dispute_id": dispute["id"],
                    "title": dispute["title"],
                    "confidence": dispute.get("confidence_score"),
                    "occurrence_count": dispute.get("occurrence_count"),
                    "source_prs": dispute.get("source_pr_ids") or [],
                }
            ],
            suggested_resolution=_generate_suggested_resolution(dispute, conflict_type),
            confidence_score=min(1.0, match_score),
        )
    
    return None


def _classify_conflict_type(tags: List[str], matched_terms: List[str]) -> str:
    """Classify the type of logic conflict."""
    type_keywords = {
        "architectural_pattern_conflict": ["architecture", "design", "pattern", "layer", "module", "dependency"],
        "security_pattern_conflict": ["security", "auth", "authentication", "token", "encrypt"],
        "naming_convention_conflict": ["naming", "convention", "variable", "function", "class"],
        "performance_conflict": ["performance", "speed", "optimize", "query", "cache"],
        "error_handling_conflict": ["error", "exception", "try", "catch", "handling"],
    }
    
    all_terms = set(tags + matched_terms)
    for conflict_type, keywords in type_keywords.items():
        if any(kw in all_terms for kw in keywords):
            return conflict_type
    
    return "general_logic_conflict"


def _calculate_severity(match_score: float, dispute: Dict[str, Any]) -> str:
    """Calculate conflict severity based on match score and historical data."""
    base_score = match_score + (dispute.get("occurrence_count", 0) * 0.05)
    
    if base_score >= 0.8:
        return "critical"
    elif base_score >= 0.5:
        return "high"
    elif base_score >= 0.3:
        return "medium"
    else:
        return "low"


def _generate_conflict_description(
    pr: PullRequest,
    dispute: Dict[str, Any],
    matched_terms: List[str],
    discussion: List[DiscussionThread],
) -> str:
    """Generate human-readable conflict description."""
    parts = [
        f"This PR (#{pr.platform_pr_number}) may conflict with a historical team decision.",
        f"",
        f"**Historical Context ({dispute.get('title')}):**",
        f"{dispute.get('content', 'N/A')[:400]}",
    ]
    
    if matched_terms:
        parts.append(f"")
        parts.append(f"**Matching Patterns Detected:** {', '.join(list(set(matched_terms))[:8])}")
    
    relevant_comments = [
        c for c in discussion
        if any(term.lower() in c.body.lower() for term in matched_terms)
    ]
    if relevant_comments:
        parts.append(f"")
        parts.append(f"**Relevant Discussion:**")
        for c in relevant_comments[:3]:
            parts.append(f"- [{c.author}]: {c.body[:150]}...")
    
    return "\n".join(parts)


def _generate_suggested_resolution(dispute: Dict[str, Any], conflict_type: str) -> str:
    """Generate suggested resolution based on historical dispute."""
    base_resolution = (
        f"Review the historical decision documented in this dispute. "
        f"Consider whether the current approach aligns with team consensus. "
        f"If intentionally deviating, document the reasoning clearly."
    )
    
    if dispute.get("examples"):
        examples = dispute["examples"]
        if examples:
            example_str = "\n".join([f"```\n{ex}\n```" for ex in examples[:2]])
            base_resolution += f"\n\n**Reference Examples from past discussions:**\n{example_str}"
    
    return base_resolution


def _calculate_overall_risk(conflicts: List[LogicConflict]) -> str:
    """Calculate overall risk level from detected conflicts."""
    if not conflicts:
        return "low"
    
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for c in conflicts:
        severity_counts[c.severity] += 1
    
    if severity_counts["critical"] > 0:
        return "critical"
    elif severity_counts["high"] > 0:
        return "high"
    elif severity_counts["medium"] > 0:
        return "medium"
    else:
        return "low"


def _generate_check_summary(conflicts: List[LogicConflict], overall_risk: str) -> str:
    """Generate human-readable summary of the dialectic check."""
    if not conflicts:
        return (
            "No logic conflicts detected. This PR appears consistent with "
            "historical team decisions and architectural patterns."
        )
    
    parts = [
        f"Detected {len(conflicts)} potential logic conflict(s). ",
        f"Overall risk level: **{overall_risk.upper()}**",
        "",
    ]
    
    for i, conflict in enumerate(conflicts, 1):
        parts.append(
            f"{i}. [{conflict.severity.upper()}] {conflict.title} "
            f"(confidence: {(conflict.confidence_score * 100):.0f}%)"
        )
    
    return "\n".join(parts)


async def _check_repo_access(repo_id: int, user: User, db: AsyncSession) -> Repository:
    from sqlalchemy import select, and_
    result = await db.execute(
        select(Repository).where(
            and_(Repository.id == repo_id, Repository.owner_id == user.id)
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


async def run_dialectic_check_in_background(
    db: AsyncSession,
    pr: PullRequest,
    repository: Repository,
) -> Optional[DialecticCheckResult]:
    """
    Run dialectic check during PR processing (called from webhook).
    Returns the check result for integration into the AI review.
    """
    try:
        discussion_thread = await _extract_discussion_thread(db, pr.id)
        
        historical_disputes = await _get_historical_disputes(db, repository.id)
        
        conflicts = await _detect_logic_conflicts(
            pr=pr,
            discussion=discussion_thread,
            historical_disputes=historical_disputes,
            db=db,
        )
        
        overall_risk = _calculate_overall_risk(conflicts)
        summary = _generate_check_summary(conflicts, overall_risk)
        
        result = DialecticCheckResult(
            pr_id=pr.id,
            pr_number=pr.platform_pr_number,
            status="completed",
            conflicts=conflicts,
            summary=summary,
            overall_risk=overall_risk,
            check_timestamp=datetime.utcnow().isoformat(),
        )
        
        logger.info(
            "dialectic_check_completed",
            pr_id=pr.id,
            conflict_count=len(conflicts),
            overall_risk=overall_risk,
        )
        
        return result
        
    except Exception as e:
        logger.error("dialectic_check_failed", error=str(e), pr_id=pr.id)
        return None
