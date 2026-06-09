from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, status

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead


async def send_verification_email(email: str, token: str) -> None:
    # Placeholder for actual background email dispatch
    print(f"[BACKGROUND] Sending verification email to {email} with token: {token}")


async def send_password_reset_email(email: str, token: str) -> None:
    # Placeholder for actual background email dispatch
    print(f"[BACKGROUND] Sending password reset email to {email} with token: {token}")


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
        user_dict = await self.user_repo.get_by_email(email)
        if not user_dict:
            return None

        user = User(**user_dict)
        
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
