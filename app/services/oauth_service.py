import urllib.parse
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.models.user import OAuthAccount, OAuthProvider, User
from app.repositories.user_repo import UserRepository

settings = get_settings()

OAUTH_CONFIGS = {
    OAuthProvider.google: {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scope": "openid email profile",
    },
    OAuthProvider.github: {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "scope": "user:email",
    },
    OAuthProvider.linkedin: {
        "auth_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_url": "https://api.linkedin.com/v2/userinfo",
        "client_id": settings.linkedin_client_id,
        "client_secret": settings.linkedin_client_secret,
        "scope": "openid profile email",
    },
    OAuthProvider.facebook: {
        "auth_url": "https://www.facebook.com/v25.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v25.0/oauth/access_token",
        "userinfo_url": "https://graph.facebook.com/me",
        "client_id": settings.facebook_app_id,
        "client_secret": settings.facebook_app_secret,
        "scope": "public_profile email",
    },
}


class OAuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def get_authorization_url(self, provider: OAuthProvider) -> str:
        config = OAUTH_CONFIGS.get(provider)
       
        if not config or not config["client_id"]:
            raise HTTPException(status_code=400, detail=f"{provider.value} OAuth is not configured")

        redirect_uri = f"{settings.oauth_redirect_base_url}/{provider.value}/callback"

        params = {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": config["scope"],
        }

        if provider == OAuthProvider.google:
            params["access_type"] = "offline"
            params["prompt"] = "consent"

        query = urllib.parse.urlencode(params)
        return f"{config['auth_url']}?{query}"

    async def exchange_code_for_user_info(self, provider: OAuthProvider, code: str) -> dict[str, Any]:
        config = OAUTH_CONFIGS.get(provider)
        if not config or not config["client_id"]:
            raise HTTPException(status_code=400, detail=f"{provider.value} OAuth is not configured")

        redirect_uri = f"{settings.oauth_redirect_base_url}/{provider.value}/callback"

        async with httpx.AsyncClient() as client:
            # 1. Exchange code for access token
            data = {
                "code": code,
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": redirect_uri,
            }

            if provider in (OAuthProvider.google, OAuthProvider.linkedin):
                data["grant_type"] = "authorization_code"

            headers = {"Accept": "application/json"}
            
            if provider == OAuthProvider.facebook:
                token_response = await client.get(config["token_url"], params=data)
            elif provider == OAuthProvider.linkedin:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                token_response = await client.post(config["token_url"], data=data, headers=headers)
            else:
                token_response = await client.post(config["token_url"], data=data, headers=headers)

            if token_response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Failed to exchange code: {token_response.text}")

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail="Failed to parse access token")

            # 2. Fetch user info
            userinfo_headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "cinema-event-system",
                "Accept": "application/vnd.github.v3+json" if provider == OAuthProvider.github else "application/json"
            }
            
            if provider == OAuthProvider.facebook:
                userinfo_response = await client.get(
                    config["userinfo_url"],
                    params={"fields": "id,name,first_name,last_name,email", "access_token": access_token}
                )
            else:
                userinfo_response = await client.get(config["userinfo_url"], headers=userinfo_headers)
                

            if userinfo_response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Failed to fetch user info: {userinfo_response.text}")

            userinfo = userinfo_response.json()

            if provider == OAuthProvider.google:
                name = userinfo.get("name")
                provider_id = userinfo.get("id", userinfo.get("sub"))
            elif provider == OAuthProvider.github:
                name = userinfo.get("name") or userinfo.get("login")
                provider_id = str(userinfo.get("id"))
            elif provider == OAuthProvider.linkedin:
                name = userinfo.get("name")
                provider_id = userinfo.get("sub")
            elif provider == OAuthProvider.facebook:
                name = userinfo.get("name")
                provider_id = userinfo.get("id")
            else:
                name = "OAuth User"
                provider_id = "unknown"

            # Normalize user info mapping
            email = userinfo.get("email")
            
            if provider == OAuthProvider.github and not email:
                emails_response = await client.get("https://api.github.com/user/emails", headers=userinfo_headers)
                if emails_response.status_code == 200:
                    emails = emails_response.json()
                    primary = next((e for e in emails if e.get("primary")), None)
                    if primary:
                        email = primary.get("email")
                        
            if not email:
                if provider == OAuthProvider.github:
                    email = f"{provider_id}@github.local"
                else:
                    raise HTTPException(status_code=400, detail=f"No email provided by {provider.value}")

            return {
                "email": email,
                "name": name,
                "provider": provider,
                "provider_user_id": provider_id,
                "access_token": access_token
            }

    async def upsert_oauth_user(self, profile: dict[str, Any]) -> User:
        email = profile['email']
        provider_user_id = profile['provider_user_id']
        provider = profile['provider']
        access_token = profile['access_token']
        
        user_dict = await self.user_repo.get_by_email(email)
        
        oauth_account = OAuthAccount(
            provider=provider,
            provider_user_id=provider_user_id,
            access_token=access_token
        )

        if user_dict:
            user = User(**user_dict)
            exists = False
            for acc in user.oauth_accounts:
                if acc.provider == provider and acc.provider_user_id == provider_user_id:
                    acc.access_token = access_token
                    exists = True
                    break
            
            if not exists:
                user.oauth_accounts.append(oauth_account)
                
            await self.user_repo.update(user.id, {"oauth_accounts": [acc.model_dump() for acc in user.oauth_accounts]})
            return user
        else:
            user = User(
                email=email,
                full_name=profile['name'] or email.split('@')[0],
                is_verified=True,
                oauth_accounts=[oauth_account]
            )
            await self.user_repo.create(user)
            return user
