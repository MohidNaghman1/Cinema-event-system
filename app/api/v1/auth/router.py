import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.security import decode_token, is_token_revoked, revoke_token, create_access_token, hash_password
from app.dependencies import get_user_repo
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, Token
from app.schemas.user import UserCreate, UserRead
from app.services.auth_service import AuthService, send_password_reset_email

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
    payload = decode_token(data.refresh_token)
    jti = payload.get("jti")
    sub = payload.get("sub")

    if not jti or not sub:
        raise HTTPException(status_code=401, detail="Invalid token format")

    if await is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    user_dict = await auth_service.user_repo.get_by_id(sub)
    if not user_dict:
        raise HTTPException(status_code=401, detail="User not found")

    user = User(**user_dict)
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")

    return auth_service.issue_tokens(user)


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


@router.post("/verify-email")
async def verify_email(
    token: str,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    payload = decode_token(token)
    if payload.get("type") != "verify_email":
        raise HTTPException(status_code=400, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    user_dict = await auth_service.user_repo.get_by_id(user_id)
    if not user_dict:
        raise HTTPException(status_code=404, detail="User not found")

    user = User(**user_dict)
    if user.is_verified:
        return {"detail": "Email already verified"}

    await auth_service.user_repo.update(user_id, {"is_verified": True})
    return {"detail": "Email verified successfully"}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    user_dict = await auth_service.user_repo.get_by_email(data.email)
    if user_dict:
        user = User(**user_dict)
        reset_token = create_access_token(
            {"sub": str(user.id), "type": "reset_password"},
            expires_delta=datetime.timedelta(minutes=15),
        )
        background_tasks.add_task(send_password_reset_email, user.email, reset_token)

    return {"detail": "If the email is registered, a password reset link has been sent."}


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    payload = decode_token(data.token)
    if payload.get("type") != "reset_password":
        raise HTTPException(status_code=400, detail="Invalid token type")

    user_id = payload.get("sub")
    jti = payload.get("jti")
    
    if not user_id or not jti:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    if await is_token_revoked(jti):
        raise HTTPException(status_code=400, detail="Token has already been used")

    hashed_password = hash_password(data.new_password)
    await auth_service.user_repo.update(user_id, {"hashed_password": hashed_password})

    # Revoke the reset token so it can't be reused
    exp = payload.get("exp")
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if exp:
        ttl = int(exp - now)
        if ttl > 0:
            await revoke_token(jti, ttl)

    return {"detail": "Password reset successfully"}
