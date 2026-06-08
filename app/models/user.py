from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from beanie import before_event, Document, Update, Save
from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class OAuthProvider(str, Enum):
    google = "google"
    github = "github"
    facebook = "facebook"
    linkedin = "linkedin"


class OAuthAccount(BaseModel):
    provider: OAuthProvider
    provider_user_id: str
    access_token: str = Field(description="Encrypted at rest")


class User(Document):
    id: UUID = Field(default_factory=uuid4)
    email: str = Field(unique=True, index=True)
    hashed_password: Optional[str] = None
    full_name: str
    phone: Optional[str] = None
    profile_picture: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False
    role: Role = Role.USER
    oauth_accounts: list[OAuthAccount] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @before_event(Update)
    @before_event(Save)
    def update_updated_at(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    class Settings:
        name = "users"
        use_state_management = True
