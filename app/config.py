from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env files."""

    app_name: str = "cinema-event-system"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "cinema_event_system"
    mongo_max_pool_size: int = 50
    mongo_min_pool_size: int = 5
    mongo_server_selection_timeout_ms: int = 5000
    
    jwt_secret: str = "default-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: list[str] = Field(default_factory=list)
    log_level: str = "INFO"

    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    facebook_app_id: str | None = None
    facebook_app_secret: str | None = None
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    oauth_redirect_base_url: str = "http://localhost:8000/api/v1/auth/oauth"
    
    stripe_api_key: str | None = None
    stripe_webhook_secret: str | None = None
    
    mail_provider: str = "postmark"  
    email_host: str = "smtp.gmail.com"
    email_port: int = 587
    email_use_tls: bool = True
    email_host_user: str | None = None
    email_host_password: str | None = None
    sendgrid_api_key: str | None = None
    postmark_api_token: str | None = None
    default_from_email: str = "noreply@cinema-events.com"
    frontend_url: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [item.strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
