"""Approval platform API (Unified Approval Workflow System).

- Approver seed master data (Section 1): list / upsert / resolve approvers for
  a document context.
- AI/deterministic rule engine (Section 2): evaluate rules on a context.
- Workflow definition lifecycle (Section 3): publish / archive.
- Approval audit + SLA (Section 4): events, SLA definitions/metrics, breaches,
  analytics.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.approval import (
    get_approver_seed,
    list_approver_seeds,
    resolve_approvers_for_context,
    upsert_approver_seed,
)
from app.crud.workflow import get_workflow_definition, set_workflow_definition_status
from app.database.session import get_db
from app.models.user import User
from app.services.approval_audit import (
    evaluate_sla_breaches,
    get_approval_analytics,
    get_approval_events,
    get_sla_metrics,
)
from app.models.user import UserRole
from app.services.approval_rule_engine import evaluate_rules, explain_decision
from app.utils.dependencies import get_current_active_user

router = APIRouter(prefix="/approval", tags=["Approval"])
workflow_router = APIRouter(prefix="/workflow", tags=["Workflow"])


def _require_admin(current_user: User) -> None:
    """Same admin-gate pattern as routers/budget.py and org_structure.py."""
    if current_user.role != UserRole.ADMINISTRATOR and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only administrators can manage approver master data"
        )


def _seed_to_dict(seed) -> dict:
    return {
        "id": str(seed.id),
        "user_id": str(seed.user_id),
        "display_name": seed.display_name,
        "email": seed.email,
        "role_code": seed.role_code,
        "org_unit_id": seed.org_unit_id,
        "approval_limit_currency": seed.approval_limit_currency,
        "approval_limit_amount": str(seed.approval_limit_amount) if seed.approval_limit_amount is not None else None,
        "category_scope": seed.category_scope,
        "supplier_scope": seed.supplier_scope,
        "is_primary_approver": seed.is_primary_approver,
        "backup_approver_user_id": str(seed.backup_approver_user_id) if seed.backup_approver_user_id else None,
        "delegation_start_date": seed.delegation_start_date.isoformat() if seed.delegation_start_date else None,
        "delegation_end_date": seed.delegation_end_date.isoformat() if seed.delegation_end_date else None,
        "active_flag": seed.active_flag,
    }


# --- Approver seeds (Section 1) -------------------------------------------


@router.get("/approvers", summary="List approver seeds")
async def list_approvers_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    role_code: Optional[str] = Query(None),
    org_unit_id: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    seeds = await list_approver_seeds(
        db,
        tenant_id=current_user.tenant_id,
        role_code=role_code,
        org_unit_id=org_unit_id,
        active_only=not include_inactive,
        skip=skip,
        limit=limit,
    )
    return {"items": [_seed_to_dict(s) for s in seeds], "total": len(seeds)}


@router.post("/approvers", summary="Upsert an approver seed", status_code=status.HTTP_201_CREATED)
async def upsert_approver_endpoint(
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        seed = await upsert_approver_seed(db, data=payload, actor_id=current_user.id, tenant_id=current_user.tenant_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _seed_to_dict(seed)


@router.get("/approvers/resolve", summary="Resolve approvers for a document context")
async def resolve_approvers_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    role_code: str = Query(...),
    amount: Decimal = Query(0),
    category: Optional[str] = Query(None),
    supplier_id: Optional[str] = Query(None),
) -> dict:
    approvers = await resolve_approvers_for_context(
        db,
        role_code=role_code,
        amount=amount,
        category=category,
        supplier_id=supplier_id,
        tenant_id=current_user.tenant_id,
    )
    return {"role_code": role_code, "approvers": approvers, "count": len(approvers)}


@router.get("/approvers/{approver_seed_id}", summary="Get a single approver seed")
async def get_approver_endpoint(
    approver_seed_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    seed = await get_approver_seed(db, approver_seed_id, tenant_id=current_user.tenant_id)
    if seed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approver seed not found")
    return _seed_to_dict(seed)


@router.patch("/approvers/{approver_seed_id}", summary="Update an approver seed (admin only)")
async def update_approver_endpoint(
    approver_seed_id: UUID,
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(current_user)
    seed = await get_approver_seed(db, approver_seed_id, tenant_id=current_user.tenant_id)
    if seed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approver seed not found")
    # user_id + role_code are the upsert key -- changing them here would
    # silently create a second row instead of updating this one. Deactivate
    # and create a new seed instead.
    for key_field in ("user_id", "role_code"):
        if key_field in payload and str(payload[key_field]).upper() != str(getattr(seed, key_field)).upper():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{key_field} cannot be changed; deactivate this seed and create a new one",
            )
    merged = {**payload, "user_id": str(seed.user_id), "role_code": seed.role_code}
    try:
        updated = await upsert_approver_seed(db, data=merged, actor_id=current_user.id, tenant_id=current_user.tenant_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _seed_to_dict(updated)


@router.delete("/approvers/{approver_seed_id}", summary="Deactivate an approver seed (admin only)")
async def deactivate_approver_endpoint(
    approver_seed_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(current_user)
    seed = await get_approver_seed(db, approver_seed_id, tenant_id=current_user.tenant_id)
    if seed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approver seed not found")
    # Soft-delete only: historical ApprovalEvents may reference this seed's
    # user/role, so master data with audit history is never hard-deleted.
    seed.active_flag = False
    seed.updated_by = current_user.id
    await db.commit()
    await db.refresh(seed)
    return _seed_to_dict(seed)


# --- Rule engine (Section 2) ----------------------------------------------


@router.post("/rules/evaluate", summary="Evaluate deterministic + AI approval rules")
async def evaluate_rules_endpoint(
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    document_type = payload.get("document_type") or "procurement_requisition"
    document_context = payload.get("document_context") or {}
    workflow_context = payload.get("workflow_context") or {}
    approver_user_ids = payload.get("approver_user_ids") or []
    approvers = [{"user_id": str(u), "role_code": payload.get("role_code", "")} for u in approver_user_ids] or None
    decision = evaluate_rules(document_type, document_context, workflow_context, approvers)
    decision["explanation"] = explain_decision(decision)
    return decision


# --- Workflow definition lifecycle (Section 3) ----------------------------


@workflow_router.post("/{definition_id}/publish", summary="Publish a workflow definition")
async def publish_workflow_definition_endpoint(
    definition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    definition = await get_workflow_definition(db, definition_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow definition not found")
    updated = await set_workflow_definition_status(db, definition_id, status="published")
    return {"id": str(updated.id), "status": updated.status}


@workflow_router.post("/{definition_id}/archive", summary="Archive a workflow definition")
async def archive_workflow_definition_endpoint(
    definition_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    definition = await get_workflow_definition(db, definition_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow definition not found")
    updated = await set_workflow_definition_status(db, definition_id, status="archived")
    return {"id": str(updated.id), "status": updated.status}


# --- Approval audit + SLA (Section 4) -------------------------------------


@router.get("/events", summary="List approval audit events")
async def list_approval_events_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    document_type: Optional[str] = Query(None),
    document_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    events = await get_approval_events(
        db, tenant_id=current_user.tenant_id, document_type=document_type, document_id=document_id, limit=limit
    )
    return {
        "items": [
            {
                "id": str(e.id),
                "document_type": e.document_type,
                "document_id": str(e.document_id),
                "node_type": e.node_type,
                "action": e.action,
                "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
                "actor_role_code": e.actor_role_code,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "comments": e.comments,
                "ai_flags": e.ai_flags,
            }
            for e in events
        ],
        "total": len(events),
    }


@router.get("/sla/metrics", summary="List SLA metrics")
async def list_sla_metrics_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    document_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    metrics = await get_sla_metrics(db, tenant_id=current_user.tenant_id, document_id=document_id, limit=limit)
    return {
        "items": [
            {
                "id": str(m.id),
                "document_id": str(m.document_id),
                "node_id": m.node_id,
                "actual_duration_minutes": m.actual_duration_minutes,
                "breach_flag": m.breach_flag,
                "breach_reason": m.breach_reason,
            }
            for m in metrics
        ],
        "total": len(metrics),
    }


@router.get("/sla/definitions", summary="List SLA definitions")
async def list_sla_definitions_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
    document_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    from sqlalchemy import select

    from app.models.approval import SlaDefinition

    query = select(SlaDefinition)
    if current_user.tenant_id is not None:
        query = query.where(SlaDefinition.tenant_id == current_user.tenant_id)
    if document_type:
        query = query.where(SlaDefinition.document_type == document_type)
    query = query.order_by(SlaDefinition.document_type, SlaDefinition.created_at.desc()).limit(limit)
    result = await db.execute(query)
    definitions = list(result.scalars().all())
    return {
        "items": [
            {
                "id": str(d.id),
                "document_type": d.document_type,
                "node_type": d.node_type,
                "role_code": d.role_code,
                "target_duration_minutes": d.target_duration_minutes,
                "severity": d.severity,
            }
            for d in definitions
        ],
        "total": len(definitions),
    }


@router.post("/sla/definitions", summary="Upsert an SLA definition", status_code=status.HTTP_201_CREATED)
async def upsert_sla_definition_endpoint(
    payload: dict,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.models.approval import SlaDefinition

    sla = SlaDefinition(
        tenant_id=current_user.tenant_id,
        document_type=str(payload.get("document_type")),
        node_type=payload.get("node_type"),
        role_code=payload.get("role_code"),
        target_duration_minutes=int(payload.get("target_duration_minutes", 60)),
        severity=str(payload.get("severity", "WARNING")),
    )
    db.add(sla)
    await db.commit()
    await db.refresh(sla)
    return {
        "id": str(sla.id),
        "document_type": sla.document_type,
        "role_code": sla.role_code,
        "target_duration_minutes": sla.target_duration_minutes,
        "severity": sla.severity,
    }


@router.post("/sla/evaluate-breaches", summary="Evaluate SLA breaches (scheduled job / on-demand)")
async def evaluate_sla_breaches_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    breached = await evaluate_sla_breaches(db)
    return {"breached_tasks": [str(t.id) for t in breached], "count": len(breached)}


@router.get("/analytics", summary="Approval SLA analytics & reporting")
async def approval_analytics_endpoint(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_approval_analytics(db)
