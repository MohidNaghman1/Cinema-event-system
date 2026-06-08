from typing import Any

from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, status

from app.config import get_settings
from app.models.user import OAuthAccount, OAuthProvider, User
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService

settings = get_settings()
oauth = OAuth()

if settings.google_client_id and settings.google_client_secret:
    oauth.register(
        name='google',
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

if settings.github_client_id and settings.github_client_secret:
    oauth.register(
        name='github',
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email read:user'}
    )

if settings.facebook_app_id and settings.facebook_app_secret:
    oauth.register(
        name='facebook',
        client_id=settings.facebook_app_id,
        client_secret=settings.facebook_app_secret,
        access_token_url='https://graph.facebook.com/v15.0/oauth/access_token',
        authorize_url='https://www.facebook.com/v15.0/dialog/oauth',
        api_base_url='https://graph.facebook.com/v15.0/',
        client_kwargs={'scope': 'email public_profile'}
    )

if settings.linkedin_client_id and settings.linkedin_client_secret:
    oauth.register(
        name='linkedin',
        client_id=settings.linkedin_client_id,
        client_secret=settings.linkedin_client_secret,
        access_token_url='https://www.linkedin.com/oauth/v2/accessToken',
        authorize_url='https://www.linkedin.com/oauth/v2/authorization',
        api_base_url='https://api.linkedin.com/v2/',
        client_kwargs={'scope': 'r_liteprofile r_emailaddress'}
    )


class OAuthService:
    def __init__(self, user_repo: UserRepository, auth_service: AuthService) -> None:
        self.user_repo = user_repo
        self.auth_service = auth_service

    async def get_user_profile(self, provider: str, token: dict[str, Any]) -> dict[str, Any]:
        client = oauth.create_client(provider)
        if not client:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Provider {provider} not supported")
            
        profile: dict[str, Any] = {}
        if provider == 'google':
            resp = await client.get('https://openidconnect.googleapis.com/v1/userinfo', token=token)
            data = resp.json()
            profile = {
                'provider_user_id': data.get('sub'),
                'email': data.get('email'),
                'full_name': data.get('name'),
                'profile_picture': data.get('picture')
            }
        elif provider == 'github':
            resp = await client.get('user', token=token)
            data = resp.json()
            email = data.get('email')
            if not email:
                emails_resp = await client.get('user/emails', token=token)
                emails_data = emails_resp.json()
                for e in emails_data:
                    if e.get('primary') and e.get('verified'):
                        email = e.get('email')
                        break
            profile = {
                'provider_user_id': str(data.get('id')),
                'email': email,
                'full_name': data.get('name') or data.get('login'),
                'profile_picture': data.get('avatar_url')
            }
        elif provider == 'facebook':
            resp = await client.get('me?fields=id,name,email,picture', token=token)
            data = resp.json()
            profile = {
                'provider_user_id': data.get('id'),
                'email': data.get('email'),
                'full_name': data.get('name'),
                'profile_picture': data.get('picture', {}).get('data', {}).get('url')
            }
        elif provider == 'linkedin':
            resp = await client.get('me', token=token)
            data = resp.json()
            email_resp = await client.get('emailAddress?q=members&projection=(elements*(handle~))', token=token)
            email_data = email_resp.json()
            
            email = None
            if email_data.get('elements'):
                email = email_data['elements'][0].get('handle~', {}).get('emailAddress')
                
            first_name = data.get('localizedFirstName', '')
            last_name = data.get('localizedLastName', '')
            
            profile = {
                'provider_user_id': data.get('id'),
                'email': email,
                'full_name': f"{first_name} {last_name}".strip(),
                'profile_picture': None
            }
            
        if not profile.get('email'):
            raise HTTPException(status_code=400, detail="Could not retrieve email from OAuth provider")
            
        return profile

    async def upsert_oauth_user(self, provider: str, profile: dict[str, Any], access_token: str) -> User:
        email = profile['email']
        provider_user_id = profile['provider_user_id']
        
        user_dict = await self.user_repo.get_by_email(email)
        
        oauth_account = OAuthAccount(
            provider=OAuthProvider(provider),
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
                full_name=profile['full_name'] or email.split('@')[0],
                profile_picture=profile['profile_picture'],
                is_verified=True,
                oauth_accounts=[oauth_account]
            )
            await self.user_repo.create(user)
            return user
