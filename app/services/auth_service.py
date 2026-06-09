from datetime import timedelta
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, status

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead
from app.services.email_service import send_verification_email, send_password_reset_email


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def register_user(
        self, data: UserCreate, background_tasks: BackgroundTasks
    ) -> UserRead:
        existing_user = await self.user_repo.get_by_email(data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        hashed_password = hash_password(data.password)
        
        user = User(
            email=data.email,
            hashed_password=hashed_password,
            full_name=data.full_name,
            phone=data.phone,
        )
        
        await self.user_repo.create(user)

        # Generate a specific short-lived verification token
        verification_token = create_access_token(
            {"sub": str(user.id), "type": "verify_email"},
            expires_delta=timedelta(hours=24),
        )

        background_tasks.add_task(send_verification_email, user.email, verification_token)

        return UserRead.model_validate(user)

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        user = await self.user_repo.get_by_email(email)
        if not user:
            return None

        if not user.hashed_password or not verify_password(password, user.hashed_password):
            return None

        return user

    def issue_tokens(self, user: User) -> Token:
        access_token = create_access_token(
            {"sub": str(user.id), "role": user.role.value}
        )
        refresh_token = create_refresh_token(
            {"sub": str(user.id), "role": user.role.value}
        )
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    async def verify_email(self, token: str) -> None:
        payload = decode_token(token)
        if payload.get("type") != "verify_email":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token payload",
            )

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found",
            )

        if user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already verified",
            )

        await self.user_repo.update(user_id, {"is_verified": True})

    async def request_password_reset(
        self, email: str, background_tasks: BackgroundTasks
    ) -> None:
        user = await self.user_repo.get_by_email(email)
        if not user:
            return

        reset_token = create_access_token(
            {"sub": str(user.id), "type": "reset_password"},
            expires_delta=timedelta(hours=1),
        )
        background_tasks.add_task(send_password_reset_email, user.email, reset_token)

    async def reset_password(self, token: str, new_password: str) -> None:
        payload = decode_token(token)
        if payload.get("type") != "reset_password":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token payload",
            )

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found",
            )

        hashed_password = hash_password(new_password)
        await self.user_repo.update(user_id, {"hashed_password": hashed_password})

    async def refresh_access_token(self, refresh_token: str) -> Token:
        payload = decode_token(refresh_token)

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return self.issue_tokens(user)