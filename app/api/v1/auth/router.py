import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_token, revoke_token
from app.dependencies import get_user_repo
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})
limiter = Limiter(key_func=get_remote_address)
bearer_scheme = HTTPBearer()


def get_auth_service(user_repo: UserRepository = Depends(get_user_repo)) -> AuthService:
    return AuthService(user_repo)


@router.post("/register", response_model=UserRead)
async def register(
    request: Request,
    data: UserCreate,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserRead:
    return await auth_service.register_user(data, background_tasks)


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Token:
    user = await auth_service.authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
        )
    return auth_service.issue_tokens(user)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh(
    data: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Token:
    return await auth_service.refresh_access_token(data.refresh_token)


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/logout")
async def logout(
    data: LogoutRequest,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, str]:
    # Extract access token payload
    access_token = credentials.credentials
    access_payload = decode_token(access_token)
    
    # Extract refresh token payload
    refresh_payload = decode_token(data.refresh_token)

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()

    # Revoke access token
    access_jti = access_payload.get("jti")
    access_exp = access_payload.get("exp")
    if access_jti and access_exp:
        ttl = int(access_exp - now)
        if ttl > 0:
            await revoke_token(access_jti, ttl)

    # Revoke refresh token
    refresh_jti = refresh_payload.get("jti")
    refresh_exp = refresh_payload.get("exp")
    if refresh_jti and refresh_exp:
        ttl = int(refresh_exp - now)
        if ttl > 0:
            await revoke_token(refresh_jti, ttl)

    return {"detail": "Logged out successfully"}


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/verify-email")
async def verify_email(
    data: VerifyEmailRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.verify_email(data.token)
    return {"detail": "Email verified successfully"}


class ForgotPasswordRequest(BaseModel):
    email: str


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.request_password_reset(data.email, background_tasks)
    return {"detail": "If the email is registered, a password reset link has been sent."}


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await auth_service.reset_password(data.token, data.new_password)
    return {"detail": "Password reset successfully"}


from app.services.oauth_service import OAuthService
from app.models.user import OAuthProvider

def get_oauth_service(user_repo: UserRepository = Depends(get_user_repo)) -> OAuthService:
    return OAuthService(user_repo)

@router.get("/oauth/{provider}/url")
async def get_oauth_url(
    provider: OAuthProvider,
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> dict[str, str]:
    """Returns the authorization URL for the requested provider."""
    url = oauth_service.get_authorization_url(provider)
    return {"url": url}

@router.get("/oauth/{provider}/callback", response_model=Token)
async def oauth_callback(
    provider: OAuthProvider,
    code: str,
    oauth_service: OAuthService = Depends(get_oauth_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> Token:
    """Exchanges the code for tokens and logs the user in."""
    profile = await oauth_service.exchange_code_for_user_info(provider, code)
    user = await oauth_service.upsert_oauth_user(profile)
    return auth_service.issue_tokens(user)
