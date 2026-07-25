"""
Security utilities for S2PNexus.

Provides password hashing and JWT token management.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from jose import jwt as jose_jwt

from jwt import ExpiredSignatureError, InvalidTokenError
from app.core.config import settings


@dataclass
class TokenData:
    """Simple token payload model used by the auth tests and helpers."""

    sub: str
    type: str

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    subject: UUID | str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
        "type": "access",
    }
    encoded_jwt = jose_jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def create_refresh_token(
    subject: UUID | str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
        "type": "refresh",
    }
    encoded_jwt = jose_jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Raises:
        jwt.JWTError: If the token is invalid, malformed, or expired.
    """
    try:
        return jose_jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except ExpiredSignatureError:
        raise
    except jose_jwt.JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc


def get_token_type(token: str) -> Optional[str]:
    """Get token type from JWT payload."""
    payload = decode_token(token)
    if payload:
        return payload.get("type")
    return None


def get_token_subject(token: str) -> Optional[UUID]:
    """Get subject (user ID) from JWT payload."""
    payload = decode_token(token)
    if payload and payload.get("sub"):
        return UUID(payload["sub"])
    return None