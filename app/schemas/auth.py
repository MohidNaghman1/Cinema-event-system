from pydantic import BaseModel, EmailStr
from app.models.user import OAuthProvider


class Token(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "access_token": "eyJhb...",
                    "refresh_token": "eyJhb...",
                    "token_type": "bearer"
                }
            ]
        }
    }

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "securepassword123"
                }
            ]
        }
    }

    email: EmailStr
    password: str


class OAuthCallbackRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "provider": "google",
                    "code": "4/0AX4XfWh...",
                    "redirect_uri": "http://localhost:3000/callback"
                }
            ]
        }
    }

    provider: OAuthProvider
    code: str
    redirect_uri: str
