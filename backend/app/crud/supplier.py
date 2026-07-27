"""
Supplier CRUD operations for S2PNexus.

Provides database operations for Supplier model.
"""

import re
from datetime import datetime, timezone
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, asc, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier import Supplier
from app.schemas.supplier import RELATIONSHIP_TYPES, SupplierCreate, SupplierUpdate

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


# --- Supplier Hierarchy -----------------------------------------------------
#
# parent_supplier_id/children are deliberately walked via explicit queries here
# rather than through the ORM relationship (see the comment on Supplier.children
# in models/supplier.py) -- keeps every hierarchy operation depth-bounded and
# defensive against a pre-existing cycle instead of relying on eager loading.


async def get_supplier_ancestor_ids(db: AsyncSession, supplier_id: UUID, *, max_depth: int = 50) -> list[UUID]:
    """Walk parent_supplier_id upward from supplier_id, closest ancestor first.
    Bounded by max_depth and a visited-set as a defensive guard -- this should
    never actually loop given set_supplier_parent's cycle check, but a direct
    DB write (migration, manual fix) could still introduce one."""
    ancestor_ids: list[UUID] = []
    visited: set[UUID] = {supplier_id}
    current = await get_supplier(db, supplier_id)
    depth = 0
    while current and current.parent_supplier_id and depth < max_depth:
        parent_id = current.parent_supplier_id
        if parent_id in visited:
            break
        ancestor_ids.append(parent_id)
        visited.add(parent_id)
        current = await get_supplier(db, parent_id)
        depth += 1
    return ancestor_ids


async def set_supplier_parent(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    parent_supplier_id: Optional[UUID],
    relationship_type: Optional[str] = None,
) -> Supplier:
    """Set (or clear, if parent_supplier_id is None) a supplier's parent in the
    corporate hierarchy. Raises ValueError on a self-parent, an unknown
    relationship_type, or a parent assignment that would create a cycle."""
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise LookupError("Supplier not found")

    if parent_supplier_id is None:
        supplier.parent_supplier_id = None
        supplier.relationship_type = None
        await db.commit()
        await db.refresh(supplier)
        return supplier

    if parent_supplier_id == supplier_id:
        raise ValueError("A supplier cannot be its own parent")

    parent = await get_supplier(db, parent_supplier_id)
    if not parent:
        raise LookupError("Parent supplier not found")

    if relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError(f"relationship_type must be one of: {', '.join(RELATIONSHIP_TYPES)}")

    # This supplier can't already be an ancestor of the proposed parent -- if it
    # were, attaching it below that parent would close a loop.
    ancestor_ids = await get_supplier_ancestor_ids(db, parent_supplier_id)
    if supplier_id in ancestor_ids:
        raise ValueError("Setting this parent would create a cycle in the supplier hierarchy")

    supplier.parent_supplier_id = parent_supplier_id
    supplier.relationship_type = relationship_type
    await db.commit()
    await db.refresh(supplier)
    return supplier


async def get_supplier_children(db: AsyncSession, supplier_id: UUID) -> list[Supplier]:
    result = await db.execute(select(Supplier).where(Supplier.parent_supplier_id == supplier_id))
    return list(result.scalars().all())


async def get_supplier_descendant_ids(db: AsyncSession, supplier_id: UUID) -> list[UUID]:
    """Every descendant (children, grandchildren, ...) of supplier_id, via
    breadth-first traversal. Visited-set guards against a pre-existing cycle."""
    descendant_ids: list[UUID] = []
    visited: set[UUID] = {supplier_id}
    queue: list[UUID] = [supplier_id]
    while queue:
        current_id = queue.pop(0)
        for child in await get_supplier_children(db, current_id):
            if child.id in visited:
                continue
            visited.add(child.id)
            descendant_ids.append(child.id)
            queue.append(child.id)
    return descendant_ids


async def get_supplier_hierarchy(db: AsyncSession, supplier_id: UUID) -> dict[str, Any]:
    """A supplier's immediate hierarchy context: its parent (if any) and direct
    children -- one level in each direction, not the full tree."""
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise LookupError("Supplier not found")

    parent_node = None
    if supplier.parent_supplier_id:
        parent = await get_supplier(db, supplier.parent_supplier_id)
        if parent:
            parent_node = {"id": parent.id, "name": parent.name, "relationship_type": supplier.relationship_type}

    children_nodes = [
        {"id": child.id, "name": child.name, "relationship_type": child.relationship_type}
        for child in await get_supplier_children(db, supplier_id)
    ]

    return {"supplier_id": supplier_id, "parent": parent_node, "children": children_nodes}


async def get_supplier_spend_rollup(db: AsyncSession, supplier_id: UUID) -> dict[str, Any]:
    """Total spend for a supplier plus every descendant in its hierarchy (the
    "global spend roll-up" capability). Reuses ProcurementInvoice the same way
    crud/spend.py's forecast does: total_amount when set, falling back to the
    always-required amount field otherwise."""
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise LookupError("Supplier not found")

    from app.models.procurement import ProcurementInvoice

    included_ids = [supplier_id] + await get_supplier_descendant_ids(db, supplier_id)
    result = await db.execute(select(ProcurementInvoice).where(ProcurementInvoice.supplier_id.in_(included_ids)))
    invoices = list(result.scalars().all())
    total_spend = sum((invoice.total_amount or invoice.amount or Decimal("0") for invoice in invoices), Decimal("0"))

    return {"supplier_id": supplier_id, "included_supplier_ids": included_ids, "total_spend": total_spend}


# --- Duplicate Management -----------------------------------------------------


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _normalize_domain(website: Optional[str]) -> Optional[str]:
    if not website:
        return None
    domain = website.lower().strip()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0]
    return domain or None


async def find_potential_duplicate_suppliers(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    min_score: float = 0.5,
    limit: int = 10,
) -> list[tuple[Supplier, float, list[str]]]:
    """Multi-factor duplicate detection for a given supplier: exact tax_id
    match, exact normalized website-domain match, and fuzzy name similarity
    (difflib -- no extra fuzzy-matching dependency needed for this pass).
    Returns (candidate, score 0-1, match_reasons) sorted by score descending.
    Already-merged suppliers are excluded (they're not distinct records anymore)."""
    supplier = await get_supplier(db, supplier_id)
    if not supplier:
        raise LookupError("Supplier not found")

    result = await db.execute(
        select(Supplier).where(Supplier.id != supplier_id, Supplier.merged_into_supplier_id.is_(None))
    )
    candidates = list(result.scalars().all())

    normalized_name = _normalize_name(supplier.name)
    normalized_domain = _normalize_domain(supplier.website)

    scored: list[tuple[Supplier, float, list[str]]] = []
    for candidate in candidates:
        score = 0.0
        reasons: list[str] = []

        if supplier.tax_id and candidate.tax_id and supplier.tax_id.strip().lower() == candidate.tax_id.strip().lower():
            score += 0.5
            reasons.append("matching tax ID")

        candidate_domain = _normalize_domain(candidate.website)
        if normalized_domain and candidate_domain and normalized_domain == candidate_domain:
            score += 0.3
            reasons.append("matching website domain")

        name_ratio = SequenceMatcher(None, normalized_name, _normalize_name(candidate.name)).ratio()
        if name_ratio >= 0.75:
            score += 0.4 * name_ratio
            reasons.append(f"similar name ({name_ratio:.0%} match)")

        score = min(score, 1.0)
        if reasons and score >= min_score:
            scored.append((candidate, score, reasons))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


async def merge_suppliers(
    db: AsyncSession,
    *,
    source_supplier_id: UUID,
    target_supplier_id: UUID,
) -> Supplier:
    """Merge a duplicate ("source") supplier record into the surviving
    ("target"/golden) record. Reassigns live Contract references to the golden
    record so ongoing/awarded work follows it; historical SupplierRequest/
    SupplierRegistration rows are deliberately left pointing at the original
    record since they document how *that* record was onboarded, not something
    a later merge decision should rewrite."""
    if source_supplier_id == target_supplier_id:
        raise ValueError("Cannot merge a supplier into itself")

    source = await get_supplier(db, source_supplier_id)
    target = await get_supplier(db, target_supplier_id)
    if not source or not target:
        raise LookupError("Supplier not found")
    if source.merged_into_supplier_id is not None:
        raise ValueError("Source supplier has already been merged into another record")
    if target.merged_into_supplier_id is not None:
        raise ValueError(
            "Cannot merge into a supplier that has itself been merged -- merge into its surviving record instead"
        )

    from app.models.contract import Contract

    await db.execute(
        update(Contract).where(Contract.supplier_id == source_supplier_id).values(supplier_id=target_supplier_id)
    )

    source.merged_into_supplier_id = target.id
    source.lifecycle_status = "merged"
    source.is_active = False

    await db.commit()
    await db.refresh(source)
    return source