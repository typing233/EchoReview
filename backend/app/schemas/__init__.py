from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from app.models import Platform


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserOut(UserBase):
    id: int
    created_at: datetime
    platforms: List[str] = []

    class Config:
        from_attributes = True


class OAuthAccountOut(BaseModel):
    id: int
    platform: Platform
    platform_user_id: str
    scopes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RepositoryBase(BaseModel):
    full_name: str
    name: str
    description: Optional[str] = None
    platform: Platform
    default_branch: str = "main"


class RepositoryCreate(RepositoryBase):
    platform_repo_id: str


class RepositoryOut(RepositoryBase):
    id: int
    platform_repo_id: str
    webhook_active: bool
    collection_enabled: bool
    last_collected_at: Optional[datetime] = None
    created_at: datetime
    pr_count: Optional[int] = None
    quality_pr_count: Optional[int] = None

    class Config:
        from_attributes = True


class PullRequestOut(BaseModel):
    id: int
    platform_pr_number: int
    title: str
    description: Optional[str] = None
    author: str
    status: str
    base_branch: str
    head_branch: str
    additions: int
    deletions: int
    review_count: int
    comment_count: int
    quality_score: Optional[float] = None
    is_quality_pr: bool
    pr_url: Optional[str] = None
    merged_at: Optional[datetime] = None
    platform_created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReviewCommentOut(BaseModel):
    id: int
    author: str
    body: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    diff_hunk: Optional[str] = None
    comment_type: str
    is_addressed: Optional[bool] = None
    addressing_commit: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    platform_created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KnowledgeItemOut(BaseModel):
    id: int
    knowledge_type: str
    title: str
    content: str
    examples: Optional[List] = None
    tags: Optional[List] = None
    file_patterns: Optional[List] = None
    confidence_score: float
    occurrence_count: int
    source_pr_ids: Optional[List] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AIReviewCommentCreate(BaseModel):
    file_path: str
    line_number: Optional[int] = None
    body: str
    severity: str = "suggestion"  # suggestion, warning, error, info
    category: str = "general"  # style, logic, security, performance, etc.
    context_explanation: Optional[str] = None
    related_knowledge_ids: Optional[List[int]] = None
    similar_pr_numbers: Optional[List[int]] = None
    suggested_fix: Optional[str] = None


class AIReviewSessionOut(BaseModel):
    id: int
    status: str
    triggered_by: str
    summary: Optional[str] = None
    overall_assessment: Optional[str] = None
    ai_comments: Optional[List] = None
    knowledge_items_used: Optional[List] = None
    similar_prs: Optional[List] = None
    posted_to_platform: bool
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CollectionRequest(BaseModel):
    days: int = 90
    min_review_comments: int = 2
    max_prs: int = 200


class WebhookPayload(BaseModel):
    action: str
    pull_request: Optional[dict] = None
    repository: Optional[dict] = None
    number: Optional[int] = None


class RepositoryListItem(BaseModel):
    """Item from GitHub/GitLab API for repository listing"""
    platform_repo_id: str
    full_name: str
    name: str
    description: Optional[str] = None
    default_branch: str = "main"
    private: bool = False
    platform: Platform
