"""
User CRUD operations for S2PNexus.

Provides database operations for User model.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email address."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Get user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# Alias for router compatibility
async def get_user(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Get user by ID (alias for get_user_by_id)."""
    return await get_user_by_id(db, user_id)


async def create_user(db: AsyncSession, user_in: UserCreate, created_by: UUID = None) -> User:
    """Create a new user."""
    user_data = user_in.model_dump()
    if created_by:
        user_data["created_by"] = created_by
    user = User(**user_data)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user_id: UUID, user_in: UserUpdate) -> User:
    """Update user by ID."""
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: UUID) -> None:
    """Delete user by ID."""
    user = await get_user_by_id(db, user_id)
    if user:
        await db.delete(user)
        await db.commit()


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    sort_by: str = "email",
    sort_order: str = "asc",
) -> list[User]:
    """Get users with pagination, optional search, and sorting."""
    query = select(User)
    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) | (User.full_name.ilike(f"%{search}%"))
        )
    sort_column = getattr(User, sort_by, User.email)
    query = query.order_by(asc(sort_column) if sort_order.lower() == "asc" else desc(sort_column))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_users_count(db: AsyncSession, search: Optional[str] = None) -> int:
    """Get total user count with optional search filter."""
    query = select(func.count(User.id))
    if search:
        query = query.where(
            (User.email.ilike(f"%{search}%")) | (User.full_name.ilike(f"%{search}%"))
        )
    result = await db.execute(query)
    return result.scalar_one()