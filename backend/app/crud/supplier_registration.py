from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.models.supplier_registration import SupplierRegistration
from app.schemas.supplier_registration import SupplierRegistrationCreate, SupplierRegistrationUpdate

# Valid lifecycle transitions: draft -> submitted -> under_review -> approved/rejected -> (cancelled at any point before approval)
_TRANSITION_MAP: dict[str, tuple[str, str]] = {
    "submit": ("submitted", "submitted"),
    "review": ("under_review", "under_review"),
    "approve": ("approved", "approved"),
    "reject": ("rejected", "rejected"),
    "cancel": ("cancelled", "cancelled"),
}


def generate_registration_number() -> str:
    """REG-{8 hex chars}. No central sequence table exists for registrations
    (unlike DocumentNumberingSequence for PR/PO) -- a random short uuid is
    collision-safe at this volume and avoids the extra round-trip a real
    sequence would need. Never all-zero (uuid4 is cryptographically random)."""
    return f"REG-{uuid4().hex[:8].upper()}"


async def get_supplier_registrations(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
    tenant_id: Optional[UUID] = None,
) -> list[SupplierRegistration]:
    query = select(SupplierRegistration)
    if status:
        query = query.where(SupplierRegistration.status == status)
    if search:
        query = query.where(
            SupplierRegistration.company_name.ilike(f"%{search}%")
            | SupplierRegistration.registration_number.ilike(f"%{search}%")
            | SupplierRegistration.primary_contact_email.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(SupplierRegistration.tenant_id == tenant_id)
    query = query.order_by(desc(SupplierRegistration.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_supplier_registrations_count(
    db: AsyncSession, status: Optional[str] = None, search: Optional[str] = None, tenant_id: Optional[UUID] = None
) -> int:
    query = select(func.count(SupplierRegistration.id))
    if status:
        query = query.where(SupplierRegistration.status == status)
    if search:
        query = query.where(
            SupplierRegistration.company_name.ilike(f"%{search}%")
            | SupplierRegistration.registration_number.ilike(f"%{search}%")
            | SupplierRegistration.primary_contact_email.ilike(f"%{search}%")
        )
    if tenant_id is not None:
        query = query.where(SupplierRegistration.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one()


async def create_supplier_registration(
    db: AsyncSession, registration_in: SupplierRegistrationCreate | dict[str, Any], tenant_id: Optional[UUID] = None
) -> SupplierRegistration:
    # Accepts either a validated schema or a plain dict (e.g. when invoked via a
    # command handler that has already unpacked the request payload).
    data = registration_in.model_dump() if hasattr(registration_in, "model_dump") else dict(registration_in)
    registration = SupplierRegistration(**data)
    if tenant_id is not None:
        registration.tenant_id = tenant_id
    db.add(registration)
    await db.commit()
    await db.refresh(registration)
    return registration


async def get_supplier_registration(
    db: AsyncSession, registration_id: UUID | str, tenant_id: Optional[UUID] = None
) -> Optional[SupplierRegistration]:
    # Callers may pass a stringified id (e.g. command objects that serialize ids as
    # strings), so normalize to a real UUID instance before binding it to the query.
    normalized_id = registration_id if isinstance(registration_id, UUID) else UUID(str(registration_id))
    query = select(SupplierRegistration).where(SupplierRegistration.id == normalized_id)
    if tenant_id is not None:
        query = query.where(SupplierRegistration.tenant_id == tenant_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_supplier_registration(
    db: AsyncSession,
    registration_id: UUID,
    registration_in: SupplierRegistrationUpdate,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierRegistration]:
    registration = await get_supplier_registration(db, registration_id, tenant_id=tenant_id)
    if not registration:
        return None
    update_data = registration_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(registration, field, value)
    await db.commit()
    await db.refresh(registration)
    return registration


async def transition_supplier_registration(
    db: AsyncSession,
    registration_id: UUID,
    *,
    actor_id: UUID,
    action: str,
    details: Optional[dict[str, Any]] = None,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierRegistration]:
    registration = await get_supplier_registration(db, registration_id, tenant_id=tenant_id)
    if not registration:
        return None

    action_key = action.lower()
    status, lifecycle_status = _TRANSITION_MAP.get(
        action_key, (registration.status, registration.lifecycle_status)
    )
    registration.status = status
    registration.lifecycle_status = lifecycle_status

    now = datetime.now(timezone.utc)
    if action_key == "submit":
        registration.approval_status = "pending"
        registration.submitted_at = now
    elif action_key == "review":
        registration.reviewed_by = actor_id
        registration.reviewed_at = now
    elif action_key == "approve":
        registration.approval_status = "approved"
        registration.approved_by = actor_id
        registration.approved_at = now
    elif action_key == "reject":
        registration.approval_status = "rejected"
        registration.rejected_by = actor_id
        registration.rejected_at = now
    elif action_key == "cancel":
        registration.approval_status = "cancelled"
        registration.cancelled_at = now

    await db.commit()
    await db.refresh(registration)
    return registration


async def convert_registration_to_supplier(
    db: AsyncSession,
    registration_id: UUID,
    *,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierRegistration]:
    """Create a Supplier record from an approved SupplierRegistration and link them."""
    registration = await get_supplier_registration(db, registration_id, tenant_id=tenant_id)
    if not registration:
        return None
    if registration.approval_status != "approved":
        raise ValueError("Only approved registrations can be converted to a supplier")
    if registration.supplier_id is not None:
        return registration

    supplier = Supplier(
        name=registration.company_name,
        description=registration.legal_name,
        contact_email=registration.primary_contact_email,
        contact_phone=registration.primary_contact_phone,
        address=", ".join(
            part
            for part in (
                registration.address_line1,
                registration.address_line2,
                registration.city,
                registration.state_province,
                registration.postal_code,
                registration.country,
            )
            if part
        ),
        website=registration.website,
        tax_id=registration.tax_id,
        payment_terms=registration.payment_terms,
        currency=registration.currency,
        is_active=True,
        created_by=actor_id,
        # Preferred Supplier composite input (Template Framework Phase 2):
        # mirror the intake risk assessment onto the live supplier record.
        current_risk_score=registration.risk_score,
        current_risk_level=registration.risk_level,
    )
    db.add(supplier)
    await db.flush()

    registration.supplier_id = supplier.id
    registration.lifecycle_status = "active"

    await db.commit()
    await db.refresh(registration)
    return registration
