"""
IDE Plugin endpoints for Copilot Agents compatibility.
Supports:
- LLM configuration (baseurl, apikey, modelname) with connectivity test
- Code standard caching via IndexedDB sync endpoint
- Local pre-review before commit
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from app.database import get_db
from app.models import (
    User, Repository, KnowledgeItem, KnowledgeType,
    PullRequest, ReviewComment,
)
from app.schemas import KnowledgeItemOut
from app.auth import get_current_user
from app.config import settings
import structlog
import json

logger = structlog.get_logger()
router = APIRouter(prefix="/ide", tags=["ide"])


class LLMConfig(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    provider: str = "openai"


class LLMConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None


class LLMTestRequest(BaseModel):
    base_url: str
    api_key: str
    model_name: str = "gpt-3.5-turbo"
    provider: str = "openai"


class PreReviewRequest(BaseModel):
    repo_id: int
    files: List[Dict[str, Any]]
    diff_content: Optional[str] = None
    branch: Optional[str] = None


class SyncRequest(BaseModel):
    repo_id: int
    last_sync_at: Optional[str] = None


class SyncResponse(BaseModel):
    items: List[KnowledgeItemOut]
    deleted_ids: List[int] = []
    new_sync_at: str


_user_llm_configs: Dict[int, LLMConfig] = {}


@router.get("/llm/config")
async def get_llm_config(
    current_user: User = Depends(get_current_user),
):
    """Get user's LLM configuration."""
    config = _user_llm_configs.get(current_user.id, LLMConfig(
        base_url=settings.openai_api_key and "https://api.openai.com/v1" or None,
        api_key=None,
        model_name=settings.openai_model,
        provider=settings.llm_provider,
    ))
    return {
        "base_url": config.base_url,
        "model_name": config.model_name,
        "provider": config.provider,
        "has_api_key": bool(config.api_key),
    }


@router.put("/llm/config")
async def update_llm_config(
    update: LLMConfigUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update user's LLM configuration."""
    existing = _user_llm_configs.get(current_user.id, LLMConfig())
    if update.base_url is not None:
        existing.base_url = update.base_url.rstrip("/") if update.base_url else None
    if update.api_key is not None:
        existing.api_key = update.api_key or None
    if update.model_name is not None:
        existing.model_name = update.model_name
    if update.provider is not None:
        existing.provider = update.provider
    _user_llm_configs[current_user.id] = existing
    logger.info("llm_config_updated", user_id=current_user.id, provider=existing.provider)
    return {
        "status": "ok",
        "message": "Configuration saved",
        "config": {
            "base_url": existing.base_url,
            "model_name": existing.model_name,
            "provider": existing.provider,
            "has_api_key": bool(existing.api_key),
        },
    }


@router.post("/llm/test")
async def test_llm_connection(
    request: LLMTestRequest,
    current_user: User = Depends(get_current_user),
):
    """Test LLM API connectivity."""
    try:
        import httpx
        base_url = request.base_url.rstrip("/")
        test_message = "Say 'OK' in one word."
        
        if request.provider == "anthropic":
            headers = {
                "x-api-key": request.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": request.model_name or "claude-3-opus-20240229",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": test_message}],
            }
            url = f"{base_url}/v1/messages" if "/v1" not in base_url else base_url
            if url.endswith("/messages"):
                url = url
            elif url.endswith("/v1"):
                url = f"{url}/messages"
            else:
                url = f"{base_url}/v1/messages"
        else:
            headers = {
                "Authorization": f"Bearer {request.api_key}",
                "content-type": "application/json",
            }
            payload = {
                "model": request.model_name or "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": test_message}],
                "max_tokens": 10,
            }
            url = f"{base_url}/chat/completions" if "/chat/completions" not in base_url else base_url
            if url.endswith("/v1"):
                url = f"{url}/chat/completions"
            elif "/v1" not in url and not url.endswith("/chat/completions"):
                url = f"{base_url}/v1/chat/completions"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code == 200:
                data = resp.json()
                if request.provider == "anthropic":
                    response_text = data.get("content", [{}])[0].get("text", "")
                else:
                    response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                return {
                    "status": "ok",
                    "connected": True,
                    "response": response_text.strip(),
                    "latency_ms": resp.elapsed.total_seconds() * 1000,
                }
            else:
                return {
                    "status": "error",
                    "connected": False,
                    "error": f"API returned status {resp.status_code}",
                    "details": resp.text[:500] if len(resp.text) > 500 else resp.text,
                }
                
    except httpx.ConnectError as e:
        return {
            "status": "error",
            "connected": False,
            "error": f"Connection failed: {str(e)}",
        }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "connected": False,
            "error": "Connection timeout",
        }
    except Exception as e:
        return {
            "status": "error",
            "connected": False,
            "error": str(e),
        }


@router.get("/sync/code_standards")
async def sync_code_standards(
    repo_id: int = Query(..., description="Repository ID"),
    last_sync_at: Optional[str] = Query(None, description="ISO timestamp of last sync"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get code standards for IDE IndexedDB caching.
    Returns only items updated since last_sync_at for incremental sync.
    Compatible with Copilot Agents protocol for knowledge retrieval.
    """
    from datetime import datetime, timezone
    repo = await _check_repo_access(repo_id, current_user, db)
    
    query = select(KnowledgeItem).where(
        and_(
            KnowledgeItem.repository_id == repo_id,
            KnowledgeItem.knowledge_type == KnowledgeType.CODE_STANDARD,
        )
    )
    
    if last_sync_at:
        try:
            sync_dt = datetime.fromisoformat(last_sync_at.replace("Z", "+00:00"))
            query = query.where(KnowledgeItem.updated_at > sync_dt)
        except ValueError:
            pass
    
    query = query.order_by(desc(KnowledgeItem.confidence_score * KnowledgeItem.occurrence_count))
    result = await db.execute(query)
    items = result.scalars().all()
    
    new_sync_at = datetime.now(timezone.utc).isoformat()
    
    return {
        "items": [KnowledgeItemOut.model_validate(item) for item in items],
        "total_count": len(items),
        "new_sync_at": new_sync_at,
        "repo_id": repo_id,
        "repo_name": repo.full_name,
    }


@router.get("/sync/high_frequency")
async def get_high_frequency_standards(
    repo_id: int = Query(...),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get highest frequency code standards for IDE caching.
    These are typically cached locally in IndexedDB for quick lookups.
    """
    await _check_repo_access(repo_id, current_user, db)
    
    result = await db.execute(
        select(KnowledgeItem)
        .where(
            and_(
                KnowledgeItem.repository_id == repo_id,
                KnowledgeItem.knowledge_type == KnowledgeType.CODE_STANDARD,
            )
        )
        .order_by(desc(KnowledgeItem.occurrence_count), desc(KnowledgeItem.confidence_score))
        .limit(limit)
    )
    items = result.scalars().all()
    
    return {
        "items": [KnowledgeItemOut.model_validate(item) for item in items],
        "limit": limit,
        "caching_hint": {
            "store_in_indexeddb": True,
            "ttl_hours": 24,
            "refresh_on_pr_update": True,
        },
    }


@router.post("/pre-review")
async def run_pre_review(
    request: PreReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run localized pre-review before code commit.
    Uses user-configured LLM (via /ide/llm/config) with local knowledge cache.
    Can be called directly by IDE plugins (Copilot Agents compatible).
    """
    await _check_repo_access(request.repo_id, current_user, db)
    
    user_config = _user_llm_configs.get(current_user.id)
    
    if not user_config or not user_config.api_key:
        raise HTTPException(
            status_code=400,
            detail="LLM not configured. Please set API key via /ide/llm/config first."
        )
    
    relevant_knowledge = await _get_relevant_knowledge_for_files(
        db, request.repo_id, request.files
    )
    
    review_result = await _generate_local_review(
        user_config=user_config,
        files=request.files,
        diff_content=request.diff_content,
        knowledge_items=relevant_knowledge,
    )
    
    return {
        "status": "completed",
        "review": review_result,
        "knowledge_used": [
            {"id": k.get("id"), "title": k.get("title")}
            for k in relevant_knowledge
        ],
        "pre_commit_ready": review_result.get("overall_assessment") in ["LGTM", "APPROVE_WITH_SUGGESTIONS"],
    }


async def _get_relevant_knowledge_for_files(
    db: AsyncSession,
    repo_id: int,
    files: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Get relevant knowledge items for changed files."""
    result = await db.execute(
        select(KnowledgeItem)
        .where(KnowledgeItem.repository_id == repo_id)
        .order_by(desc(KnowledgeItem.confidence_score * KnowledgeItem.occurrence_count))
        .limit(50)
    )
    all_knowledge = result.scalars().all()
    
    if not all_knowledge:
        return []
    
    file_names = [f.get("filename", f.get("path", "")) for f in files]
    relevant = []
    
    import fnmatch
    for item in all_knowledge:
        if not item.file_patterns:
            relevant.append(item)
            continue
        for pattern in item.file_patterns:
            if any(fnmatch.fnmatch(f, pattern) for f in file_names):
                relevant.append(item)
                break
    
    return [
        {
            "id": item.id,
            "knowledge_type": item.knowledge_type.value,
            "title": item.title,
            "content": item.content,
            "examples": item.examples,
            "file_patterns": item.file_patterns,
        }
        for item in relevant[:15]
    ]


async def _generate_local_review(
    user_config: LLMConfig,
    files: List[Dict[str, Any]],
    diff_content: Optional[str],
    knowledge_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generate pre-review using user-configured LLM."""
    import httpx
    
    knowledge_context = ""
    if knowledge_items:
        knowledge_context = "\n\nTeam Code Standards (from local cache):\n"
        for item in knowledge_items[:10]:
            knowledge_context += f"\n- [{item['knowledge_type'].upper()}] {item['title']}\n  {item['content'][:200]}\n"
    
    files_info = "\n".join([
        f"- {f.get('filename', f.get('path', 'unknown'))} "
        f"(+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        for f in files[:20]
    ])
    
    diff_preview = ""
    if diff_content:
        diff_preview = diff_content[:5000]
    else:
        for f in files[:5]:
            if f.get("diff"):
                diff_preview += f"\n--- {f.get('filename')} ---\n{f.get('diff')[:1000]}\n"
    
    system_prompt = """You are a senior engineer performing a pre-commit code review.
Focus on code standards, potential bugs, and style consistency.
Be concise but thorough. Respond with valid JSON only."""

    user_prompt = f"""Review these code changes before commit.

Files changed:
{files_info}

Code diff:
```diff
{diff_preview}
```
{knowledge_context}

Return JSON with:
{{
  "summary": "2-3 sentence summary",
  "overall_assessment": "LGTM" | "NEEDS_CHANGES" | "APPROVE_WITH_SUGGESTIONS",
  "comments": [
    {{
      "file_path": "path/to/file",
      "line_number": 1,
      "severity": "error" | "warning" | "suggestion" | "info",
      "body": "comment text",
      "suggested_fix": "optional code fix"
    }}
  ],
  "positive_aspects": ["what was done well"],
  "key_concerns": ["top issues"]
}}"""

    base_url = user_config.base_url.rstrip("/") if user_config.base_url else ""
    is_anthropic = user_config.provider == "anthropic"
    
    if is_anthropic:
        headers = {
            "x-api-key": user_config.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": user_config.model_name or "claude-3-sonnet-20240229",
            "max_tokens": 2000,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        url = f"{base_url}/v1/messages" if "/v1" in base_url else f"{base_url}/v1/messages"
        if url.endswith("/v1"):
            url = f"{url}/messages"
    else:
        headers = {
            "Authorization": f"Bearer {user_config.api_key}",
            "content-type": "application/json",
        }
        payload = {
            "model": user_config.model_name or "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
        }
        url = f"{base_url}/chat/completions"
        if url.endswith("/v1"):
            url = f"{url}/chat/completions"
        elif "/v1" not in url:
            url = f"{base_url}/v1/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                if is_anthropic:
                    content = data.get("content", [{}])[0].get("text", "{}")
                else:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                return json.loads(content)
            else:
                return {
                    "summary": f"LLM API error: {resp.status_code}",
                    "overall_assessment": "NEEDS_CHANGES",
                    "comments": [],
                    "positive_aspects": [],
                    "key_concerns": [f"API request failed: {resp.text[:200]}"],
                }
    except Exception as e:
        logger.error("local_review_failed", error=str(e))
        return {
            "summary": "Pre-review failed due to LLM error",
            "overall_assessment": "NEEDS_CHANGES",
            "comments": [],
            "positive_aspects": [],
            "key_concerns": [str(e)],
        }


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
