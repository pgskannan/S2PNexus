"""
Users router for S2PNexus.

Handles user management operations (admin only).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.crud.user import get_user, get_users, get_users_count, update_user, delete_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate, UserListResponse, UserDirectoryEntry, UserDirectoryResponse
from app.utils.dependencies import get_current_active_superuser, get_current_active_user

router = APIRouter(prefix="/users", tags=["Users"])
settings = get_settings()


@router.get(
    "/directory",
    response_model=UserDirectoryResponse,
    summary="List users (directory)",
    description=(
        "Lightweight user directory (id/full_name/email only) available to any "
        "authenticated user -- for resolving a requested_by/assignee_id UUID to a "
        "display name in things like requisition lists and approval-flow diagrams. "
        "Unlike GET /users, this is NOT admin-only, and deliberately excludes "
        "role/is_superuser/tenant_id and other fields regular users shouldn't see "
        "about each other. Registered before /{user_id} so 'directory' isn't "
        "swallowed as a user_id path param."
    ),
)
async def list_users_directory(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(500, ge=1, le=1000),
    search: str | None = Query(None, description="Filter by email or full name substring"),
) -> UserDirectoryResponse:
    users = await get_users(db, skip=0, limit=limit, search=search)
    return UserDirectoryResponse(items=[UserDirectoryEntry.model_validate(u) for u in users])


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users",
    description="Get paginated list of users (admin only)",
)
async def list_users(
    current_user: Annotated[User, Depends(get_current_active_superuser)],
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    search: str | None = Query(None, description="Search by email or full name"),
    sort_by: str = Query("email", description="Sort field"),
    sort_order: str = Query("asc", description="Sort direction (asc/desc)"),
) -> UserListResponse:
    """
    List all users with pagination.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records
        current_user: Current admin user
        db: Database session

    Returns:
        UserListResponse: Paginated user list
    """
    users = await get_users(
        db,
        skip=skip,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = await get_users_count(db, search=search)

    return UserListResponse(
        items=[UserResponse.model_validate(user) for user in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Get user details by ID (admin only)",
)
async def get_user_by_id(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_superuser)],
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Get user by ID.

    Args:
        user_id: User UUID
        current_user: Current admin user
        db: Database session

    Returns:
        UserResponse: User details

    Raises:
        HTTPException: If user not found
    """
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user",
    description="Update user details (admin only)",
)
async def update_user_by_id(
    user_id: UUID,
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_superuser)],
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Update user by ID.

    Args:
        user_id: User UUID
        user_update: User update data
        current_user: Current admin user
        db: Database session

    Returns:
        UserResponse: Updated user details

    Raises:
        HTTPException: If user not found
    """
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    updated_user = await update_user(db, user_id, user_update)
    return UserResponse.model_validate(updated_user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete user by ID (admin only)",
)
async def delete_user_by_id(
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_superuser)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete user by ID.

    Args:
        user_id: User UUID
        current_user: Current admin user
        db: Database session

    Raises:
        HTTPException: If user not found or trying to delete self
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await delete_user(db, user_id)