"""CRUD helpers for Address book (Phase 1)."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import Address
from app.models.document_numbering import NO_TENANT_ID


def _effective_tenant_id(tenant_id: Optional[UUID]) -> UUID:
    return tenant_id if tenant_id is not None else NO_TENANT_ID


async def list_addresses_for_user(db: AsyncSession, user_id: UUID, tenant_id: Optional[UUID]) -> List[Address]:
    # A user's own addresses must always be visible to them regardless of their
    # current tenant_id (e.g. if they were reassigned to a different tenant after
    # the address was created) -- so owner_type == "user" is not tenant-scoped.
    # Tenant-shared addresses ARE scoped to the caller's current tenant.
    eff = _effective_tenant_id(tenant_id)
    stmt = select(Address).where(
        ((Address.owner_type == "tenant") & (Address.tenant_id == eff))
        | ((Address.owner_type == "user") & (Address.owner_id == user_id))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_default_address_for_user(db: AsyncSession, user_id: UUID) -> Optional[Address]:
    stmt = select(Address).where(Address.owner_type == "user", Address.owner_id == user_id, Address.is_default == True)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_address_for_lookup(
    db: AsyncSession, address_id: UUID, user_id: UUID, tenant_id: Optional[UUID]
) -> Optional[Address]:
    """Fetch a single address, applying the same visibility rule as
    list_addresses_for_user (own personal addresses, or the caller's tenant's
    shared addresses). Used when another domain (e.g. purchase orders) needs to
    resolve a client-supplied address_id -- returns None rather than raising so
    callers can turn that into their own domain-appropriate error."""
    eff = _effective_tenant_id(tenant_id)
    stmt = select(Address).where(
        Address.id == address_id,
        ((Address.owner_type == "tenant") & (Address.tenant_id == eff))
        | ((Address.owner_type == "user") & (Address.owner_id == user_id)),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


_NOT_CLIENT_ASSIGNABLE = {"id", "tenant_id", "owner_type", "owner_id"}


async def create_address(db: AsyncSession, *, tenant_id: Optional[UUID], owner_type: str, owner_id: Optional[UUID], **fields) -> Address:
    eff = _effective_tenant_id(tenant_id)
    # Drop any of these if they leaked in via a raw request-body dict spread from a
    # router (e.g. POST /mine passing **payload) -- tenant_id/owner_type/owner_id
    # must only ever come from the server-derived kwargs above, never from client
    # input, or a client could try to create an address under another tenant/owner.
    safe_fields = {k: v for k, v in fields.items() if k not in _NOT_CLIENT_ASSIGNABLE}
    addr = Address(tenant_id=eff, owner_type=owner_type, owner_id=owner_id, **safe_fields)
    db.add(addr)
    await db.commit()
    await db.refresh(addr)
    return addr


async def _get_owned_address(db: AsyncSession, address_id: UUID, owner_id: UUID) -> Address:
    """Fetch an address, enforcing that it is a personal address owned by owner_id.

    Treats "exists but belongs to someone else" the same as "does not exist"
    (raises the same ValueError -> callers map this to 404, not 403) so we don't
    leak whether a given address_id belongs to another user.
    """
    result = await db.execute(select(Address).where(Address.id == address_id))
    addr = result.scalar_one_or_none()
    if addr is None or addr.owner_type != "user" or addr.owner_id != owner_id:
        raise ValueError("Address not found")
    return addr


async def update_address(db: AsyncSession, address_id: UUID, updates: dict, *, owner_id: UUID) -> Address:
    addr = await _get_owned_address(db, address_id, owner_id)
    for k, v in updates.items():
        if k in _NOT_CLIENT_ASSIGNABLE:
            # Prevent a PATCH payload from reassigning ownership/tenant via raw dict fields.
            continue
        setattr(addr, k, v)
    await db.commit()
    await db.refresh(addr)
    return addr


async def delete_address(db: AsyncSession, address_id: UUID, *, owner_id: UUID) -> None:
    addr = await _get_owned_address(db, address_id, owner_id)
    await db.delete(addr)
    await db.commit()


async def set_default_address(db: AsyncSession, owner_id: UUID, address_id: UUID) -> Address:
    addr = await _get_owned_address(db, address_id, owner_id)

    # unset other defaults for this owner
    await db.execute(
        update(Address)
        .where(Address.owner_type == "user", Address.owner_id == owner_id, Address.is_default == True)
        .values(is_default=False)
    )
    addr.is_default = True
    await db.commit()
    await db.refresh(addr)
    return addr
