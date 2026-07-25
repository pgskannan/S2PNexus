"""Compatibility shim for auth dependencies used by routers."""

from app.core.dependencies import (
    get_current_active_superuser,
    get_current_active_user,
    get_current_tenant_id,
    get_current_user,
    get_optional_current_user,
    require_permission,
)

__all__ = [
    "get_current_active_superuser",
    "get_current_active_user",
    "get_current_tenant_id",
    "get_current_user",
    "get_optional_current_user",
    "require_permission",
]
