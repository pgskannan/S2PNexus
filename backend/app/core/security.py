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


def create_act_as_token(
    *,
    target_user_id: UUID | str,
    admin_user_id: UUID | str,
    session_id: UUID | str,
    expires_delta: timedelta,
) -> str:
    """Create a short-lived impersonation access token.

    `sub` is the TARGET user's id -- get_current_user/get_current_active_user
    resolve off `sub` with no other changes needed, so every existing
    authorization/data-visibility check in the app transparently applies as
    the impersonated user. `act_as_admin_id` / `act_as_session_id` are extra
    claims only read by app.core.security.get_act_as_claims (used for the
    "acting as" banner and the self-service session-end endpoint) -- they
    don't affect standard token decoding/validation. `type` stays "access" on
    purpose so this token is accepted anywhere a normal access token is.
    """
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    to_encode = {
        "sub": str(target_user_id),
        "exp": expire,
        "iat": now,
        "type": "access",
        "act_as_admin_id": str(admin_user_id),
        "act_as_session_id": str(session_id),
    }
    return jose_jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@dataclass
class ActAsClaims:
    admin_user_id: str
    session_id: str


def get_act_as_claims(token: str) -> Optional[ActAsClaims]:
    """Returns the impersonation claims on this token, or None if it's a
    normal (non-impersonation) access token. Never raises for malformed/
    expired tokens -- callers that need strict validation should decode the
    token themselves first; this is meant for "is this request currently
    impersonating" checks where a bad token has already been rejected
    upstream by get_current_user."""
    try:
        payload = decode_token(token)
    except Exception:
        return None
    admin_id = payload.get("act_as_admin_id")
    session_id = payload.get("act_as_session_id")
    if not admin_id or not session_id:
        return None
    return ActAsClaims(admin_user_id=admin_id, session_id=session_id)


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