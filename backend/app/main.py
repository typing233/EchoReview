from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog
from app.config import settings
from app.database import init_db
from app.api import auth, repositories, prs, knowledge, webhooks

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", app=settings.app_name)
    await init_db()
    yield
    logger.info("shutdown")


app = FastAPI(
    title="EchoReview API",
    description="AI-powered Code Review platform with GitHub/GitLab integration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router, prefix="/api")
app.include_router(repositories.router, prefix="/api")
app.include_router(prs.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
