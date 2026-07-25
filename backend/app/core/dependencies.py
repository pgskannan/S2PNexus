"""
FastAPI dependencies for S2PNexus.

Provides dependency injection for database, authentication, RBAC, and authorization.
"""

from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token, get_token_subject
from app.crud.user import get_user_by_id
from app.database.database import get_db
from app.models.user import User, UserRole

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise credentials_exception

    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise credentials_exception

    user_id = get_token_subject(token)
    if not user_id:
        raise credentials_exception

    user = await get_user_by_id(db, user_id)
    if not user:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Get current active superuser (bypasses all RBAC)."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_current_tenant_id(
    current_user: User = Depends(get_current_active_user),
) -> Optional[UUID]:
    """Return the authenticated user's tenant, or None if they aren't tenant-scoped.

    Deliberately reads current_user.tenant_id (freshly loaded from the DB on every
    request via get_current_user -> get_user_by_id) rather than a JWT claim, so a
    tenant reassignment takes effect immediately rather than only after re-login.

    Returning None means "not tenant-scoped" -- callers should treat that as
    backward-compatible unfiltered access (today's single-tenant behavior), not as
    "tenant zero".
    """
    return current_user.tenant_id


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user if authenticated, otherwise None."""
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# RBAC permission helpers
# ---------------------------------------------------------------------------

RolePermissionMap: dict[UserRole, set[str]] = {
    UserRole.ADMINISTRATOR: {
        "procurement:read", "procurement:write", "procurement:approve",
        "supplier:read", "supplier:write", "supplier:approve",
        "contract:read", "contract:write", "contract:approve",
        "sourcing:read", "sourcing:write", "sourcing:approve",
        "analytics:read",
        "users:manage",
        "workflow:admin",
    },
    UserRole.PROCUREMENT_MANAGER: {
        "procurement:read", "procurement:write", "procurement:approve",
        "supplier:read",
        "contract:read",
        "sourcing:read",
        "analytics:read",
    },
    UserRole.BUYER: {
        "procurement:read", "procurement:write",
        "supplier:read",
        "contract:read",
        "sourcing:read",
        "analytics:read",
    },
    UserRole.REQUESTER: {
        "procurement:read", "procurement:write",
        "supplier:read",
    },
    UserRole.SUPPLIER_MANAGER: {
        "supplier:read", "supplier:write", "supplier:approve",
        "contract:read",
        "analytics:read",
    },
    UserRole.CATEGORY_MANAGER: {
        "procurement:read", "procurement:write",
        "supplier:read", "supplier:write",
        "contract:read",
        "sourcing:read", "sourcing:write",
        "analytics:read",
    },
    UserRole.AP_CLERK: {
        "procurement:read",
        "supplier:read",
        "contract:read",
        "analytics:read",
    },
    UserRole.CONTRACT_MANAGER: {
        "contract:read", "contract:write", "contract:approve",
        "supplier:read",
        "analytics:read",
        "metadata:read",
    },
    UserRole.ADMINISTRATOR: {
        "procurement:read", "procurement:write", "procurement:approve",
        "supplier:read", "supplier:write", "supplier:approve",
        "contract:read", "contract:write", "contract:approve",
        "sourcing:read", "sourcing:write", "sourcing:approve",
        "analytics:read",
        "users:manage",
        "workflow:admin",
        "metadata:read", "metadata:write",
    },
    UserRole.PROCUREMENT_MANAGER: {
        "procurement:read", "procurement:write", "procurement:approve",
        "supplier:read",
        "contract:read",
        "sourcing:read",
        "analytics:read",
        "metadata:read",
    },
    UserRole.BUYER: {
        "procurement:read", "procurement:write",
        "supplier:read",
        "contract:read",
        "sourcing:read",
        "analytics:read",
        "metadata:read",
    },
    UserRole.REQUESTER: {
        "procurement:read", "procurement:write",
        "supplier:read",
        "metadata:read",
    },
    UserRole.SUPPLIER_MANAGER: {
        "supplier:read", "supplier:write", "supplier:approve",
        "contract:read",
        "analytics:read",
        "metadata:read",
    },
    UserRole.CATEGORY_MANAGER: {
        "procurement:read", "procurement:write",
        "supplier:read", "supplier:write",
        "contract:read",
        "sourcing:read", "sourcing:write",
        "analytics:read",
        "metadata:read", "metadata:write",
    },
    UserRole.AP_CLERK: {
        "procurement:read",
        "supplier:read",
        "contract:read",
        "analytics:read",
        "metadata:read",
    },
    UserRole.CONTRACT_MANAGER: {
        "contract:read", "contract:write", "contract:approve",
        "supplier:read",
        "analytics:read",
        "metadata:read",
    },
}


def require_permission(permission: str):
    """Dependency factory that checks the current user's role grants the given permission.

    Superuser bypasses all checks. Usage::

        @router.get(...)
        async def list_suppliers(
            current_user: Annotated[User, Depends(require_permission("supplier:read"))],
            ...
        )
    """
    async def _require_permission(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.is_superuser:
            return current_user
        allowed = RolePermissionMap.get(current_user.role, set())
        if permission not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' lacks permission '{permission}'",
            )
        return current_user
    return _require_permission