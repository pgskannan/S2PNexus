"""
Supplier CRUD operations for S2PNexus.

Provides database operations for Supplier model.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate

# Valid post-onboarding lifecycle transitions for an active Supplier record.
# Keyed by action name -> (allowed source states, destination state).
# Mirrors the pattern used for SupplierRegistration/SupplierRequest transitions
# in crud/supplier_registration.py and crud/supplier_request.py.
_LIFECYCLE_TRANSITION_MAP: dict[str, tuple[set[str], str]] = {
    "begin_monitoring": ({"active"}, "under_monitoring"),
    "flag_requalification": ({"active", "under_monitoring"}, "requalification_due"),
    "start_requalification": ({"requalification_due"}, "requalification_in_progress"),
    "complete_requalification": ({"requalification_in_progress"}, "active"),
    "start_offboarding": (
        {"active", "under_monitoring", "requalification_due", "requalification_in_progress"},
        "offboarding",
    ),
    "complete_offboarding": ({"offboarding"}, "offboarded"),
    "reactivate": ({"offboarded"}, "active"),
}


async def get_supplier(db: AsyncSession, supplier_id: UUID) -> Optional[Supplier]:
    """Get supplier by ID."""
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    return result.scalar_one_or_none()


async def get_suppliers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> list[Supplier]:
    """Get suppliers with pagination, filtering, search, and sorting."""
    query = select(Supplier)
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if search:
        query = query.where(
            (Supplier.name.ilike(f"%{search}%"))
            | (Supplier.description.ilike(f"%{search}%"))
            | (Supplier.contact_email.ilike(f"%{search}%"))
        )
    sort_column = getattr(Supplier, sort_by, Supplier.name)
    query = query.order_by(asc(sort_column) if sort_order.lower() == "asc" else desc(sort_column))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_suppliers_count(
    db: AsyncSession,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
) -> int:
    """Get total supplier count with optional filters."""
    query = select(func.count(Supplier.id))
    if is_active is not None:
        query = query.where(Supplier.is_active == is_active)
    if search:
        query = query.where(
            (Supplier.name.ilike(f"%{search}%"))
            | (Supplier.description.ilike(f"%{search}%"))
            | (Supplier.contact_email.ilike(f"%{search}%"))
        )
    result = await db.execute(query)
    return result.scalar_one()


async def create_supplier(
    db: AsyncSession,
    supplier_in: SupplierCreate,
    created_by: UUID,
) -> Supplier:
    """Create a new supplier."""
    supplier = Supplier(**supplier_in.model_dump(), created_by=created_by)
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def update_supplier(
    db: AsyncSession,
    supplier_id: UUID,
    supplier_in: SupplierUpdate,
) -> Optional[Supplier]:
    """Update supplier by ID."""
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        return None
    update_data = supplier_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier, field, value)
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def delete_supplier(db: AsyncSession, supplier_id: UUID) -> None:
    """Delete supplier by ID."""
    supplier = await get_supplier(db, supplier_id)
    if supplier:
        await db.delete(supplier)
        await db.commit()


async def transition_supplier_lifecycle(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    action: str,
    reason: Optional[str] = None,
    next_requalification_due_at: Optional[datetime] = None,
) -> Supplier:
    """Move a Supplier through its post-onboarding lifecycle state machine.

    Covers the Continuous Monitoring / Requalification / Offboarding stages
    of the supplier lifecycle that aren't part of the onboarding/registration
    flow. Raises ValueError on an unknown action or an invalid transition
    from the supplier's current state, so callers (the router) can turn that
    into a 400 rather than silently no-op-ing.
    """
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise LookupError("Supplier not found")

    action_key = action.lower()
    transition = _LIFECYCLE_TRANSITION_MAP.get(action_key)
    if transition is None:
        raise ValueError(f"Unknown lifecycle action '{action}'")

    allowed_from, to_state = transition
    if supplier.lifecycle_status not in allowed_from:
        raise ValueError(
            f"Cannot '{action_key}' a supplier in lifecycle state '{supplier.lifecycle_status}' "
            f"(requires one of: {', '.join(sorted(allowed_from))})"
        )
    # Validate before mutating anything: raising after the state (or any other
    # field) has already been changed on the in-session ORM object would leave
    # it mutated-but-uncommitted, and a subsequent call in the same session
    # would see that stale in-memory state via SQLAlchemy's identity map even
    # though nothing was ever persisted.
    if action_key == "start_offboarding" and not reason:
        raise ValueError("A reason is required to start offboarding")

    now = datetime.now(timezone.utc)
    supplier.lifecycle_status = to_state

    if action_key == "flag_requalification":
        supplier.next_requalification_due_at = next_requalification_due_at or now
    elif action_key == "complete_requalification":
        supplier.last_qualified_at = now
        supplier.next_requalification_due_at = None
    elif action_key == "start_offboarding":
        supplier.offboarding_reason = reason
    elif action_key == "complete_offboarding":
        supplier.offboarded_at = now
        supplier.is_active = False
    elif action_key == "reactivate":
        supplier.offboarded_at = None
        supplier.offboarding_reason = None
        supplier.is_active = True

    await db.commit()
    await db.refresh(supplier)
    return supplier


async def get_suppliers_requalification_due(
    db: AsyncSession,
    as_of: Optional[datetime] = None,
) -> list[Supplier]:
    """Suppliers whose next_requalification_due_at has passed and that aren't
    already mid-requalification or offboarding. Meant to back a periodic sweep
    (or an on-demand API call, since this codebase has no background scheduler
    yet -- same pattern as workflow.escalate_overdue_tasks)."""
    cutoff = as_of or datetime.now(timezone.utc)
    query = select(Supplier).where(
        Supplier.next_requalification_due_at.is_not(None),
        Supplier.next_requalification_due_at <= cutoff,
        Supplier.lifecycle_status.in_(["active", "under_monitoring", "requalification_due"]),
    )
    result = await db.execute(query)
    return list(result.scalars().all())