import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import get_settings
from app.core.security import redis_client
from app.dependencies import get_user_repo
from app.repositories.user_repo import UserRepository
from app.schemas.auth import Token
from app.services.auth_service import AuthService
from app.services.oauth_service import OAuthService, oauth

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})
settings = get_settings()


def get_auth_service(user_repo: UserRepository = Depends(get_user_repo)) -> AuthService:
    return AuthService(user_repo)


def get_oauth_service(
    user_repo: UserRepository = Depends(get_user_repo),
    auth_service: AuthService = Depends(get_auth_service),
) -> OAuthService:
    return OAuthService(user_repo, auth_service)


@router.get("/{provider}/authorize")
async def authorize(provider: str, request: Request) -> Any:
    """Redirect to provider authorization URL with anti-CSRF state."""
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    redirect_uri = f"{settings.oauth_redirect_base_url}/{provider}/callback"
    state = secrets.token_urlsafe(32)

    await redis_client.setex(f"oauth_state:{state}", 600, provider)

    return await client.authorize_redirect(request, redirect_uri, state=state)


@router.get("/{provider}/callback", response_model=Token)
async def callback(
    provider: str,
    request: Request,
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> Token:
    """Exchange code for tokens, upsert user, and issue internal JWT tokens."""
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    stored_provider = await redis_client.get(f"oauth_state:{state}")
    if not stored_provider or stored_provider != provider:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    await redis_client.delete(f"oauth_state:{state}")

    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    try:
        token = await client.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    profile = await oauth_service.get_user_profile(provider, token)
    access_token = token.get("access_token")

    user = await oauth_service.upsert_oauth_user(provider, profile, access_token)

    return oauth_service.auth_service.issue_tokens(user)
