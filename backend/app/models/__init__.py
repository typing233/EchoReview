import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, ForeignKey,
    Enum as SAEnum, JSON, Float, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.database import Base
from app.config import settings


class Platform(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class PRStatus(str, enum.Enum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeType(str, enum.Enum):
    CODE_STANDARD = "code_standard"
    COMMON_ISSUE = "common_issue"
    HISTORICAL_DISPUTE = "historical_dispute"
    PROJECT_CONTEXT = "project_context"
    BEST_PRACTICE = "best_practice"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    oauth_accounts: Mapped[List["OAuthAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    repositories: Mapped[List["Repository"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("platform", "platform_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[Platform] = mapped_column(SAEnum(Platform))
    platform_user_id: Mapped[str] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="oauth_accounts")


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("platform", "platform_repo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform: Mapped[Platform] = mapped_column(SAEnum(Platform))
    platform_repo_id: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(512), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    webhook_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    webhook_active: Mapped[bool] = mapped_column(Boolean, default=False)
    collection_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_collected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner: Mapped["User"] = relationship(back_populates="repositories")
    pull_requests: Mapped[List["PullRequest"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    knowledge_items: Mapped[List["KnowledgeItem"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class PullRequest(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("repository_id", "platform_pr_number"),
        Index("idx_pr_repo_quality", "repository_id", "is_quality_pr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    platform_pr_number: Mapped[int] = mapped_column(Integer)
    platform_pr_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(1024))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[str] = mapped_column(String(255))
    status: Mapped[PRStatus] = mapped_column(SAEnum(PRStatus))
    base_branch: Mapped[str] = mapped_column(String(255))
    head_branch: Mapped[str] = mapped_column(String(255))
    base_sha: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    head_sha: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    diff_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    files_changed: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_quality_pr: Mapped[bool] = mapped_column(Boolean, default=False)
    pr_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    platform_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="pull_requests")
    review_comments: Mapped[List["ReviewComment"]] = relationship(back_populates="pull_request", cascade="all, delete-orphan")
    review_sessions: Mapped[List["AIReviewSession"]] = relationship(back_populates="pull_request", cascade="all, delete-orphan")


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), index=True)
    platform_comment_id: Mapped[str] = mapped_column(String(255), unique=True)
    author: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    diff_hunk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    line_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    original_line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_type: Mapped[str] = mapped_column(String(50), default="line")  # line, general, review
    parent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # for threaded comments
    # Adoption tracking: was this comment addressed in a subsequent commit?
    is_addressed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    addressing_commit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    addressing_diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Context: surrounding code at time of comment
    context_before: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(settings.embedding_dimensions), nullable=True)
    platform_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pull_request: Mapped["PullRequest"] = relationship(back_populates="review_comments")


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    knowledge_type: Mapped[KnowledgeType] = mapped_column(SAEnum(KnowledgeType))
    title: Mapped[str] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text)
    examples: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # code examples
    source_pr_ids: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # contributing PR IDs
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    file_patterns: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # e.g. ["*.py", "services/*"]
    confidence_score: Mapped[float] = mapped_column(Float, default=0.8)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(settings.embedding_dimensions), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    repository: Mapped["Repository"] = relationship(back_populates="knowledge_items")


class AIReviewSession(Base):
    __tablename__ = "ai_review_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pull_request_id: Mapped[int] = mapped_column(ForeignKey("pull_requests.id"), index=True)
    status: Mapped[ReviewStatus] = mapped_column(SAEnum(ReviewStatus), default=ReviewStatus.PENDING)
    triggered_by: Mapped[str] = mapped_column(String(50), default="webhook")  # webhook, manual
    ai_comments: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # generated review comments
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    overall_assessment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    knowledge_items_used: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    similar_prs: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_to_platform: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    pull_request: Mapped["PullRequest"] = relationship(back_populates="review_sessions")
