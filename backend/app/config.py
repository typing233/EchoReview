from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "EchoReview"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Database
    database_url: str = "postgresql+asyncpg://echoreview:echoreview@localhost:5432/echoreview"
    database_url_sync: str = "postgresql://echoreview:echoreview@localhost:5432/echoreview"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:3000/auth/github/callback"

    # GitLab OAuth
    gitlab_client_id: str = ""
    gitlab_client_secret: str = ""
    gitlab_redirect_uri: str = "http://localhost:3000/auth/gitlab/callback"
    gitlab_base_url: str = "https://gitlab.com"

    # LLM
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    llm_provider: str = "openai"  # openai or anthropic

    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Webhook
    webhook_secret: str = "change-me-webhook-secret"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Backend public URL (used for webhook registration)
    backend_url: str = "http://localhost:8000"

    # PR Collection
    pr_collection_days: int = 90  # collect PRs from last N days
    pr_min_review_comments: int = 2  # minimum review comments for "quality" PR
    pr_max_diff_chars: int = 50000  # max chars to store for diff content

    def model_post_init(self, __context: object) -> None:
        """Validate critical settings."""
        if not self.debug and self.secret_key == "change-me-in-production":
            import warnings
            warnings.warn(
                "SECRET_KEY is set to the default insecure value. "
                "Please set a strong SECRET_KEY in production.",
                stacklevel=2,
            )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
