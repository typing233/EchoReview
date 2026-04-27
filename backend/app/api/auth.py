"""
OAuth endpoints for GitHub and GitLab authentication.
"""
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User, OAuthAccount, Platform
from app.schemas import UserOut, TokenOut
from app.auth import create_access_token, get_current_user
from app.services import github as github_svc
from app.services import gitlab as gitlab_svc
from app.config import settings
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory state store (use Redis in production)
_state_store: dict = {}


@router.get("/github/url")
async def github_oauth_url():
    """Get GitHub OAuth authorization URL."""
    state = secrets.token_urlsafe(32)
    _state_store[state] = "github"
    url = github_svc.get_oauth_url(state)
    return {"url": url, "state": state}


@router.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth callback, create/update user."""
    if state not in _state_store:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    del _state_store[state]

    # Exchange code for token
    try:
        token_data = await github_svc.exchange_code_for_token(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token received")

    # Get user info from GitHub
    try:
        gh_client = github_svc.GitHubClient(access_token)
        gh_user = await gh_client.get_user()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    platform_user_id = str(gh_user["id"])
    username = gh_user.get("login", "")
    email = gh_user.get("email")
    display_name = gh_user.get("name") or username
    avatar_url = gh_user.get("avatar_url")

    # Find or create user
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.platform == Platform.GITHUB,
            OAuthAccount.platform_user_id == platform_user_id,
        )
    )
    oauth_account = result.scalar_one_or_none()

    if oauth_account:
        # Update token
        oauth_account.access_token = access_token
        user_result = await db.execute(select(User).where(User.id == oauth_account.user_id))
        user = user_result.scalar_one()
        user.avatar_url = avatar_url
        user.display_name = display_name
    else:
        # Create user
        user = User(
            username=username,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
        )
        db.add(user)
        await db.flush()
        oauth_account = OAuthAccount(
            user_id=user.id,
            platform=Platform.GITHUB,
            platform_user_id=platform_user_id,
            access_token=access_token,
            scopes=token_data.get("scope", ""),
        )
        db.add(oauth_account)

    await db.commit()
    await db.refresh(user)

    app_token = create_access_token(user.id)
    user_out = UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        platforms=["github"],
    )
    return TokenOut(access_token=app_token, user=user_out)


@router.get("/gitlab/url")
async def gitlab_oauth_url():
    """Get GitLab OAuth authorization URL."""
    state = secrets.token_urlsafe(32)
    _state_store[state] = "gitlab"
    url = gitlab_svc.get_oauth_url(state)
    return {"url": url, "state": state}


@router.get("/gitlab/callback")
async def gitlab_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle GitLab OAuth callback, create/update user."""
    if state not in _state_store:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    del _state_store[state]

    try:
        token_data = await gitlab_svc.exchange_code_for_token(code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token received")

    try:
        gl_client = gitlab_svc.GitLabClient(access_token)
        gl_user = await gl_client.get_user()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    platform_user_id = str(gl_user["id"])
    username = gl_user.get("username", "")
    email = gl_user.get("email")
    display_name = gl_user.get("name") or username
    avatar_url = gl_user.get("avatar_url")

    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.platform == Platform.GITLAB,
            OAuthAccount.platform_user_id == platform_user_id,
        )
    )
    oauth_account = result.scalar_one_or_none()

    if oauth_account:
        oauth_account.access_token = access_token
        user_result = await db.execute(select(User).where(User.id == oauth_account.user_id))
        user = user_result.scalar_one()
        user.avatar_url = avatar_url
        user.display_name = display_name
    else:
        # Check if GitHub user exists with same username
        existing_result = await db.execute(select(User).where(User.username == username))
        user = existing_result.scalar_one_or_none()
        if not user:
            user = User(
                username=username,
                email=email,
                display_name=display_name,
                avatar_url=avatar_url,
            )
            db.add(user)
            await db.flush()
        oauth_account = OAuthAccount(
            user_id=user.id,
            platform=Platform.GITLAB,
            platform_user_id=platform_user_id,
            access_token=access_token,
            scopes=token_data.get("scope", ""),
        )
        db.add(oauth_account)

    await db.commit()
    await db.refresh(user)

    app_token = create_access_token(user.id)
    user_out = UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        platforms=["gitlab"],
    )
    return TokenOut(access_token=app_token, user=user_out)


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user with connected platforms."""
    result = await db.execute(
        select(OAuthAccount).where(OAuthAccount.user_id == current_user.id)
    )
    accounts = result.scalars().all()
    platforms = [acc.platform.value for acc in accounts]
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        platforms=platforms,
    )
