"""
Knowledge base endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.database import get_db
from app.models import User, Repository, KnowledgeItem, KnowledgeType
from app.schemas import KnowledgeItemOut
from app.auth import get_current_user
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/{repo_id}", response_model=List[KnowledgeItemOut])
async def list_knowledge_items(
    repo_id: int,
    knowledge_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge items for a repository."""
    await _check_repo_access(repo_id, current_user, db)

    query = select(KnowledgeItem).where(KnowledgeItem.repository_id == repo_id)

    if knowledge_type:
        try:
            kt = KnowledgeType(knowledge_type)
            query = query.where(KnowledgeItem.knowledge_type == kt)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid knowledge_type: {knowledge_type}")

    query = query.order_by(
        desc(KnowledgeItem.confidence_score * KnowledgeItem.occurrence_count)
    ).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    items = result.scalars().all()
    return [KnowledgeItemOut.model_validate(item) for item in items]


@router.get("/{repo_id}/{item_id}", response_model=KnowledgeItemOut)
async def get_knowledge_item(
    repo_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_repo_access(repo_id, current_user, db)
    result = await db.execute(
        select(KnowledgeItem).where(
            and_(KnowledgeItem.id == item_id, KnowledgeItem.repository_id == repo_id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return KnowledgeItemOut.model_validate(item)


@router.delete("/{repo_id}/{item_id}", status_code=204)
async def delete_knowledge_item(
    repo_id: int,
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_repo_access(repo_id, current_user, db)
    result = await db.execute(
        select(KnowledgeItem).where(
            and_(KnowledgeItem.id == item_id, KnowledgeItem.repository_id == repo_id)
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    await db.delete(item)
    await db.commit()


@router.get("/{repo_id}/stats/summary")
async def knowledge_summary(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get knowledge base statistics for a repository."""
    await _check_repo_access(repo_id, current_user, db)

    from sqlalchemy import func
    result = await db.execute(
        select(
            KnowledgeItem.knowledge_type,
            func.count(KnowledgeItem.id).label("count"),
            func.avg(KnowledgeItem.confidence_score).label("avg_confidence"),
        )
        .where(KnowledgeItem.repository_id == repo_id)
        .group_by(KnowledgeItem.knowledge_type)
    )
    rows = result.all()

    return {
        "by_type": {
            row.knowledge_type.value: {
                "count": row.count,
                "avg_confidence": round(float(row.avg_confidence or 0), 2),
            }
            for row in rows
        },
        "total": sum(row.count for row in rows),
    }


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
