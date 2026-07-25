"""
Contract CRUD operations for S2PNexus.

Provides database operations for Contract model.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.schemas.contract import ContractCreate, ContractUpdate

# Valid lifecycle transitions for a contract's authoring/review/approval flow.
_TRANSITION_MAP: dict[str, tuple[str, str]] = {
    "submit": ("under_review", "under_review"),
    "review": ("under_review", "under_review"),
    "approve": ("approved", "approved"),
    "reject": ("rejected", "rejected"),
    "activate": ("active", "active"),
    "terminate": ("terminated", "terminated"),
}


def _normalize_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


async def get_contract(db: AsyncSession, contract_id: UUID | str) -> Optional[Contract]:
    """Get contract by ID."""
    result = await db.execute(select(Contract).where(Contract.id == _normalize_uuid(contract_id)))
    return result.scalar_one_or_none()


async def get_contracts(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    supplier_id: Optional[UUID] = None,
    search: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "asc",
) -> list[Contract]:
    """Get contracts with pagination, filtering, search, and sorting."""
    query = select(Contract)
    if status:
        query = query.where(Contract.status == status)
    if supplier_id:
        query = query.where(Contract.supplier_id == supplier_id)
    if search:
        query = query.where(
            (Contract.title.ilike(f"%{search}%"))
            | (Contract.description.ilike(f"%{search}%"))
            | (Contract.contract_number.ilike(f"%{search}%"))
        )
    sort_column = getattr(Contract, sort_by, Contract.created_at)
    query = query.order_by(asc(sort_column) if sort_order.lower() == "asc" else desc(sort_column))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_contracts_count(
    db: AsyncSession,
    status: Optional[str] = None,
    supplier_id: Optional[UUID] = None,
    search: Optional[str] = None,
) -> int:
    """Get total contract count with optional filters."""
    query = select(func.count(Contract.id))
    if status:
        query = query.where(Contract.status == status)
    if supplier_id:
        query = query.where(Contract.supplier_id == supplier_id)
    if search:
        query = query.where(
            (Contract.title.ilike(f"%{search}%"))
            | (Contract.description.ilike(f"%{search}%"))
            | (Contract.contract_number.ilike(f"%{search}%"))
        )
    result = await db.execute(query)
    return result.scalar_one()


async def create_contract(
    db: AsyncSession,
    contract_in: ContractCreate,
    created_by: UUID,
) -> Contract:
    """Create a new contract."""
    contract = Contract(**contract_in.model_dump(), created_by=created_by)
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def update_contract(
    db: AsyncSession,
    contract_id: UUID,
    contract_in: ContractUpdate,
) -> Optional[Contract]:
    """Update contract by ID."""
    contract = await get_contract(db, contract_id)
    if not contract:
        return None
    update_data = contract_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(contract, field, value)
    await db.commit()
    await db.refresh(contract)
    return contract


async def delete_contract(db: AsyncSession, contract_id: UUID) -> bool:
    """Delete contract by ID."""
    contract = await get_contract(db, contract_id)
    if not contract:
        return False
    await db.delete(contract)
    await db.commit()
    return True


async def transition_contract(
    db: AsyncSession,
    contract_id: UUID | str,
    *,
    actor_id: UUID,
    action: str,
    details: Optional[dict[str, Any]] = None,
) -> Optional[Contract]:
    """Move a contract through its authoring/review/approval/activation lifecycle."""
    contract = await get_contract(db, contract_id)
    if not contract:
        return None

    action_key = action.lower()
    status, lifecycle_status = _TRANSITION_MAP.get(action_key, (contract.status, contract.lifecycle_status))
    contract.status = status
    contract.lifecycle_status = lifecycle_status

    now = datetime.now(timezone.utc)
    if action_key == "submit":
        contract.submitted_at = now
        contract.approval_status = "pending"
    elif action_key == "review":
        contract.reviewed_by = actor_id
        contract.reviewed_at = now
    elif action_key == "approve":
        contract.approval_status = "approved"
        contract.approved_by = actor_id
        contract.approved_at = now
    elif action_key == "reject":
        contract.approval_status = "rejected"
    elif action_key == "activate":
        contract.activated_at = now
    elif action_key == "terminate":
        contract.terminated_at = now

    await db.commit()
    await db.refresh(contract)
    return contract