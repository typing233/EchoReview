"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_user_id", sa.String(255), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_user_id"),
    )

    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_repo_id", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("default_branch", sa.String(255), default="main"),
        sa.Column("webhook_id", sa.String(255), nullable=True),
        sa.Column("webhook_active", sa.Boolean, default=False),
        sa.Column("collection_enabled", sa.Boolean, default=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform", "platform_repo_id"),
    )

    op.create_table(
        "pull_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("platform_pr_number", sa.Integer, nullable=False),
        sa.Column("platform_pr_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("base_branch", sa.String(255), nullable=False),
        sa.Column("head_branch", sa.String(255), nullable=False),
        sa.Column("base_sha", sa.String(255), nullable=True),
        sa.Column("head_sha", sa.String(255), nullable=True),
        sa.Column("diff_content", sa.Text, nullable=True),
        sa.Column("files_changed", sa.JSON, nullable=True),
        sa.Column("additions", sa.Integer, default=0),
        sa.Column("deletions", sa.Integer, default=0),
        sa.Column("review_count", sa.Integer, default=0),
        sa.Column("comment_count", sa.Integer, default=0),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("is_quality_pr", sa.Boolean, default=False),
        sa.Column("pr_url", sa.String(1024), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("platform_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "platform_pr_number"),
    )

    op.create_table(
        "review_comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pull_request_id", sa.Integer, sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("platform_comment_id", sa.String(255), unique=True, nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=True),
        sa.Column("diff_hunk", sa.Text, nullable=True),
        sa.Column("line_number", sa.Integer, nullable=True),
        sa.Column("original_line", sa.Integer, nullable=True),
        sa.Column("comment_type", sa.String(50), default="line"),
        sa.Column("parent_id", sa.String(255), nullable=True),
        sa.Column("is_addressed", sa.Boolean, nullable=True),
        sa.Column("addressing_commit", sa.String(255), nullable=True),
        sa.Column("addressing_diff", sa.Text, nullable=True),
        sa.Column("context_before", sa.Text, nullable=True),
        sa.Column("context_after", sa.Text, nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("platform_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("repository_id", sa.Integer, sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("knowledge_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("examples", sa.JSON, nullable=True),
        sa.Column("source_pr_ids", sa.JSON, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("file_patterns", sa.JSON, nullable=True),
        sa.Column("confidence_score", sa.Float, default=0.8),
        sa.Column("occurrence_count", sa.Integer, default=1),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ai_review_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pull_request_id", sa.Integer, sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("triggered_by", sa.String(50), default="webhook"),
        sa.Column("ai_comments", sa.JSON, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("overall_assessment", sa.Text, nullable=True),
        sa.Column("knowledge_items_used", sa.JSON, nullable=True),
        sa.Column("similar_prs", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("posted_to_platform", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("ai_review_sessions")
    op.drop_table("knowledge_items")
    op.drop_table("review_comments")
    op.drop_table("pull_requests")
    op.drop_table("repositories")
    op.drop_table("oauth_accounts")
    op.drop_table("users")
