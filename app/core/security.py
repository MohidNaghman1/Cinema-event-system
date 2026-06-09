import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_revoked_tokens: dict[str, float] = {}


def hash_password(plain: str) -> str:
    if not isinstance(plain, str):
        raise ValueError("Password must be a string")

    if len(plain.encode("utf-8")) > 72:
        raise ValueError("Password too long for bcrypt (max 72 bytes)")

    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def is_token_revoked(jti: str) -> bool:
    expiry_timestamp = _revoked_tokens.get(jti)
    if expiry_timestamp is None:
        return False

    now = time.time()
    if expiry_timestamp <= now:
        _revoked_tokens.pop(jti, None)
        return False

    return True


async def revoke_token(jti: str, ttl: int) -> None:
    if ttl > 0:
        _revoked_tokens[jti] = time.time() + ttl


def cleanup_revoked_tokens() -> int:
    now = time.time()
    expired_jtis = [jti for jti, expiry in _revoked_tokens.items() if expiry <= now]
    for jti in expired_jtis:
        _revoked_tokens.pop(jti, None)
    return len(expired_jtis)
