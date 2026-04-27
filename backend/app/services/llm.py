"""
LLM service for knowledge extraction and review generation.
Supports OpenAI and Anthropic providers.
"""
import json
from typing import Optional, List, Dict, Any
from app.config import settings
import structlog

logger = structlog.get_logger()


def _get_openai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _get_anthropic_client():
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def get_embedding(text: str) -> List[float]:
    """Generate embedding vector for text using OpenAI."""
    client = _get_openai_client()
    # Truncate to avoid token limits
    text = text[:8000]
    resp = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dimensions,
    )
    return resp.data[0].embedding


async def _call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    """Call the configured LLM provider."""
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        client = _get_anthropic_client()
        resp = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text
    else:
        client = _get_openai_client()
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"} if "json" in user_prompt.lower() else None,
        )
        return resp.choices[0].message.content


async def extract_knowledge_from_pr(
    pr_title: str,
    pr_description: str,
    diff_content: str,
    review_comments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Analyze a PR's diff and review comments to extract reusable knowledge items.
    Returns a list of structured knowledge items.
    """
    system_prompt = """You are a senior software engineer analyzing code review data to extract reusable team knowledge.
Your goal is to identify patterns, standards, and insights from PR reviews that can help future code reviews.

Respond ONLY with valid JSON."""

    comments_text = "\n".join([
        f"- [{c.get('file_path', 'general')}:{c.get('line_number', '?')}] {c.get('author', 'reviewer')}: {c.get('body', '')}"
        + (f"\n  [ADDRESSED: {c.get('addressing_diff', '')[:200]}]" if c.get('is_addressed') else "")
        for c in review_comments[:50]
    ])

    diff_preview = diff_content[:3000] if diff_content else "(no diff available)"

    user_prompt = f"""Analyze this PR and its review comments to extract knowledge items for the team.

PR Title: {pr_title}
PR Description: {pr_description or 'N/A'}

Code Diff (preview):
```
{diff_preview}
```

Review Comments:
{comments_text}

Extract knowledge items from this PR. Return a JSON object with key "items" containing an array of:
{{
  "knowledge_type": "code_standard" | "common_issue" | "historical_dispute" | "project_context" | "best_practice",
  "title": "short title (max 80 chars)",
  "content": "detailed explanation of the knowledge item",
  "examples": ["code example 1", "code example 2"],
  "tags": ["tag1", "tag2"],
  "file_patterns": ["*.py", "services/*"],
  "confidence_score": 0.0-1.0
}}

Focus on actionable insights. Only include items where you are confident the knowledge is genuine and reusable.
Return 3-8 items maximum."""

    try:
        raw = await _call_llm(system_prompt, user_prompt, max_tokens=3000)
        # Extract JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        data = json.loads(raw)
        return data.get("items", [])
    except Exception as e:
        logger.error("knowledge_extraction_failed", error=str(e))
        return []


async def generate_pr_review(
    pr_title: str,
    pr_description: str,
    diff_content: str,
    changed_files: List[Dict[str, Any]],
    knowledge_items: List[Dict[str, Any]],
    similar_prs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Generate a comprehensive AI code review for a PR.
    Returns review comments with line-level feedback and an overall summary.
    """
    system_prompt = """You are a senior software engineer performing a thorough code review.
You have deep knowledge of this team's codebase, coding standards, and historical decisions.
Your reviews are constructive, specific, and educational. You explain WHY something is an issue
and always suggest concrete alternatives. You reference historical context when relevant.

Respond ONLY with valid JSON."""

    # Format knowledge context
    knowledge_context = ""
    if knowledge_items:
        knowledge_context = "\n\nTeam Knowledge Base (relevant patterns and standards):\n"
        for item in knowledge_items[:15]:
            knowledge_context += f"\n[{item['knowledge_type'].upper()}] {item['title']}\n{item['content'][:300]}\n"

    # Format similar PR context
    similar_context = ""
    if similar_prs:
        similar_context = "\n\nSimilar Historical PRs:\n"
        for pr in similar_prs[:5]:
            similar_context += f"\n- PR #{pr['number']}: {pr['title']}\n  Key discussion: {pr.get('key_discussion', '')[:200]}\n"

    # Prepare diff (limit size)
    diff_preview = diff_content[:6000] if diff_content else ""

    # Format file list
    files_info = "\n".join([
        f"- {f.get('filename', f.get('new_path', 'unknown'))} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
        for f in changed_files[:20]
    ])

    user_prompt = f"""Review this Pull Request as a senior engineer who knows this codebase well.

PR Title: {pr_title}
PR Description: {pr_description or 'N/A'}

Files Changed:
{files_info}

Code Diff:
```diff
{diff_preview}
```
{knowledge_context}
{similar_context}

Generate a thorough code review. Return a JSON object with:
{{
  "summary": "2-3 sentence overall assessment",
  "overall_assessment": "LGTM" | "NEEDS_CHANGES" | "APPROVE_WITH_SUGGESTIONS",
  "comments": [
    {{
      "file_path": "path/to/file",
      "line_number": 42,
      "severity": "error" | "warning" | "suggestion" | "info",
      "category": "logic" | "style" | "security" | "performance" | "maintainability" | "test" | "documentation",
      "body": "Review comment text - be specific, explain WHY, suggest HOW to fix",
      "context_explanation": "Historical context or why this matters for this project specifically",
      "suggested_fix": "Concrete code suggestion if applicable",
      "related_knowledge_ids": [],
      "similar_pr_numbers": []
    }}
  ],
  "positive_aspects": ["what was done well"],
  "key_concerns": ["top 3 issues to address"]
}}

Rules:
- Be specific about file paths and line numbers from the diff
- Reference team knowledge and historical patterns when relevant
- Explain WHY each issue matters (not just "this is wrong")
- Provide concrete fix suggestions
- Maximum 10 line-level comments, focus on important issues
- If no issues, still provide helpful suggestions for improvement"""

    try:
        raw = await _call_llm(system_prompt, user_prompt, max_tokens=4096)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        return json.loads(raw)
    except Exception as e:
        logger.error("review_generation_failed", error=str(e))
        return {
            "summary": "AI review generation encountered an error.",
            "overall_assessment": "NEEDS_CHANGES",
            "comments": [],
            "positive_aspects": [],
            "key_concerns": ["Review generation failed - please review manually"],
        }


async def consolidate_knowledge(
    existing_items: List[Dict[str, Any]],
    new_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge and deduplicate knowledge items, consolidating similar ones.
    Returns a refined list of knowledge items.
    """
    if not new_items:
        return existing_items

    system_prompt = """You are managing a team knowledge base for code reviews.
Your task is to consolidate new knowledge items with existing ones, merging duplicates and improving content.
Respond ONLY with valid JSON."""

    existing_text = json.dumps(existing_items[:20], indent=2)
    new_text = json.dumps(new_items, indent=2)

    user_prompt = f"""Consolidate these knowledge items. Merge duplicates, improve descriptions.

Existing items:
{existing_text}

New items to integrate:
{new_text}

Return JSON with key "consolidated" containing the merged list. 
Keep the best version of duplicates, increment occurrence_count for merged items.
Maximum 50 total items, prioritize by confidence_score and occurrence_count."""

    try:
        raw = await _call_llm(system_prompt, user_prompt, max_tokens=4096)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        data = json.loads(raw)
        return data.get("consolidated", existing_items + new_items)
    except Exception as e:
        logger.error("knowledge_consolidation_failed", error=str(e))
        return existing_items + new_items


async def find_similar_knowledge(
    query_text: str,
    knowledge_items: List[Dict[str, Any]],
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Find the most relevant knowledge items for a given PR diff using LLM ranking.
    """
    if not knowledge_items:
        return []

    system_prompt = """You select the most relevant knowledge items for a code review.
Respond ONLY with valid JSON."""

    items_text = "\n".join([
        f"ID {i}: [{item['knowledge_type']}] {item['title']}"
        for i, item in enumerate(knowledge_items[:30])
    ])

    user_prompt = f"""Given this PR diff context, select the most relevant knowledge items.

PR/Diff context (first 1000 chars):
{query_text[:1000]}

Available knowledge items:
{items_text}

Return JSON: {{"relevant_ids": [list of item indices, most relevant first, max {top_k}]}}"""

    try:
        raw = await _call_llm(system_prompt, user_prompt, max_tokens=256)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        data = json.loads(raw)
        ids = data.get("relevant_ids", list(range(min(top_k, len(knowledge_items)))))
        return [knowledge_items[i] for i in ids if i < len(knowledge_items)]
    except Exception:
        return knowledge_items[:top_k]
