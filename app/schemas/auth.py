from pydantic import BaseModel, EmailStr
from app.models.user import OAuthProvider


class Token(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "description": "Standard Example Payload",
                    "email": "user@example.com",
                    "name": "Main Arena",
                    "title": "Summer Festival",
                    "amount": 99.99
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
                    "description": "Standard Example Payload",
                    "email": "user@example.com",
                    "name": "Main Arena",
                    "title": "Summer Festival",
                    "amount": 99.99
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
                    "description": "Standard Example Payload",
                    "email": "user@example.com",
                    "name": "Main Arena",
                    "title": "Summer Festival",
                    "amount": 99.99
                }
            ]
        }
    }

    provider: OAuthProvider
    code: str
    redirect_uri: str
