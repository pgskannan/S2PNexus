"""Real tools for the agent framework.

Each tool is an async callable of the shape `async def tool(db, **kwargs) ->
dict | list`. Tools wrap the existing domain CRUD layer so agents can ground
their answers in real S2PNexus data instead of canned strings. Registered
into a ToolRegistry via `register_default_tools`.

Tools deliberately return small, JSON-serializable summaries (not ORM
objects) since their output gets embedded directly into an LLM prompt.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.crud.analytics import get_dashboard_metrics
from app.crud.contract import get_contracts
from app.crud.contract_lifecycle import get_overdue_obligations, get_templates
from app.crud.document import get_documents
from app.crud.procurement import get_recent_goods_receipts, get_recent_invoices, get_requisitions
from app.crud.sourcing import get_sourcing_events
from app.crud.supplier import get_suppliers
from app.crud.supplier_registration import get_supplier_registrations
from app.crud.workflow import get_my_tasks
from app.metadata_engine.repository.metadata_registry_repository import MetadataRegistryRepository


def _decimal(value: Any) -> float | None:
    return float(value) if value is not None else None


async def list_open_requisitions(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Requisitions awaiting approval, most recent first."""
    requisitions = await get_requisitions(db, limit=limit)
    pending = [r for r in requisitions if r.approval_status == "pending"] or requisitions[:limit]
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "status": r.status,
            "approval_status": r.approval_status,
            "category": r.category,
            "estimated_value": _decimal(r.estimated_value),
            "priority": r.priority,
        }
        for r in pending[:limit]
    ]


async def search_suppliers(db: Any, *, search: str | None = None, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Suppliers matching a search term (or the most recently added ones)."""
    suppliers = await get_suppliers(db, limit=limit, search=search)
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "is_active": s.is_active,
            "contact_email": s.contact_email,
            "currency": s.currency,
        }
        for s in suppliers[:limit]
    ]


async def list_expiring_contracts(db: Any, *, days: int = 30, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Active contracts ending within the given window."""
    contracts = await get_contracts(db, limit=200)
    cutoff = date.today() + timedelta(days=days)
    expiring = [
        c
        for c in contracts
        if c.status == "active" and c.end_date and date.today() <= c.end_date <= cutoff
    ]
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "contract_number": c.contract_number,
            "supplier_id": str(c.supplier_id),
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "value": _decimal(c.value),
            "lifecycle_status": c.lifecycle_status,
        }
        for c in expiring[:limit]
    ]


async def list_open_sourcing_events(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Sourcing events (RFI/RFP/RFQ/auction) still open for responses."""
    events = await get_sourcing_events(db, limit=limit, status="published")
    if not events:
        events = await get_sourcing_events(db, limit=limit)
    return [
        {
            "id": str(e.id),
            "event_number": e.event_number,
            "title": e.title,
            "event_type": e.event_type,
            "status": e.status,
            "response_due_date": e.response_due_date.isoformat() if e.response_due_date else None,
            "estimated_value": _decimal(e.estimated_value),
        }
        for e in events[:limit]
    ]


async def get_spend_summary(db: Any, **_: Any) -> dict[str, Any]:
    """Executive spend/supplier/contract summary (real aggregation, see app.crud.analytics)."""
    metrics = await get_dashboard_metrics(db)
    return {
        "total_spend": _decimal(metrics.total_spend),
        "total_suppliers": metrics.total_suppliers,
        "total_contracts": metrics.total_contracts,
        "active_contracts": metrics.active_contracts,
        "expiring_contracts": metrics.expiring_contracts,
        "pending_approvals": metrics.pending_approvals,
        "top_suppliers": [
            {"supplier_name": t.supplier_name, "total_spend": _decimal(t.total_spend)} for t in metrics.top_suppliers[:5]
        ],
        "spend_by_category": [
            {"category": c.category, "amount": _decimal(c.amount)} for c in metrics.spend_by_category[:5]
        ],
    }


async def list_my_pending_tasks(db: Any, *, actor_id: str | UUID | None = None, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Workflow approval tasks currently assigned to the requesting user."""
    if actor_id is None:
        return []
    tasks = await get_my_tasks(db, actor_id if isinstance(actor_id, UUID) else UUID(str(actor_id)), status="pending")
    return [
        {
            "id": str(t.id),
            "step_name": t.step_name,
            "status": t.status,
            "due_at": t.due_at.isoformat() if t.due_at else None,
        }
        for t in tasks[:limit]
    ]


async def search_metadata_objects(db: Any, *, search: str | None = None, tenant_id: UUID | None = None, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Find metadata object definitions available to the current tenant."""
    objects = await MetadataRegistryRepository().get_objects(db, tenant_id=tenant_id, skip=0, limit=limit, search=search)
    return [{"id": str(item.id), "name": item.name, "display_name": item.display_name, "entity_type": item.entity_type} for item in objects]


async def list_recent_documents(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Most recently added documents (no search filter -- see get_documents docstring)."""
    documents = await get_documents(db, limit=limit)
    return [
        {
            "id": str(d.id),
            "filename": d.filename,
            "document_type": d.document_type,
            "content_type": d.content_type,
            "file_size": d.file_size,
        }
        for d in documents[:limit]
    ]


async def get_operations_report(db: Any, **_: Any) -> dict[str, Any]:
    """Cross-domain operational status report (counts + approvals), distinct from the spend-focused summary."""
    metrics = await get_dashboard_metrics(db)
    return {
        "total_suppliers": metrics.total_suppliers,
        "total_contracts": metrics.total_contracts,
        "active_contracts": metrics.active_contracts,
        "expiring_contracts": metrics.expiring_contracts,
        "pending_approvals": metrics.pending_approvals,
        "total_spend": _decimal(metrics.total_spend),
    }


async def list_recent_receipts(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Recently recorded goods receipts and invoices, for matching/reconciliation review."""
    receipts = await get_recent_goods_receipts(db, limit=limit)
    invoices = await get_recent_invoices(db, limit=limit)
    return [
        {
            "type": "goods_receipt",
            "id": str(r.id),
            "receipt_number": r.receipt_number,
            "status": r.status,
            "received_quantity": r.received_quantity,
            "returned_quantity": r.returned_quantity,
        }
        for r in receipts[:limit]
    ] + [
        {
            "type": "invoice",
            "id": str(i.id),
            "invoice_number": i.invoice_number,
            "status": i.status,
            "match_status": i.match_status,
            "duplicate_status": i.duplicate_status,
            "amount": _decimal(i.total_amount or i.amount),
        }
        for i in invoices[:limit]
    ]


async def list_supplier_risk_flags(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Supplier registrations with an assigned risk score/level, highest risk first."""
    registrations = await get_supplier_registrations(db, limit=200)
    flagged = [r for r in registrations if r.risk_score is not None or r.risk_level is not None]
    flagged.sort(key=lambda r: (r.risk_score or 0), reverse=True)
    return [
        {
            "id": str(r.id),
            "company_name": r.company_name,
            "risk_score": r.risk_score,
            "risk_level": r.risk_level,
            "approval_status": r.approval_status,
        }
        for r in flagged[:limit]
    ]


async def list_contract_templates(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Active contract templates and clause library entries available for authoring."""
    templates = await get_templates(db, limit=limit, is_active=True)
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "contract_type": t.contract_type,
            "is_active": t.is_active,
        }
        for t in templates[:limit]
    ]


async def list_overdue_contract_obligations(db: Any, *, limit: int = 5, **_: Any) -> list[dict[str, Any]]:
    """Contract obligations past their due date and still pending -- a concrete contract-risk signal."""
    obligations = await get_overdue_obligations(db)
    return [
        {
            "id": str(o.id),
            "contract_id": str(o.contract_id),
            "description": getattr(o, "description", None),
            "due_date": o.due_date.isoformat() if o.due_date else None,
            "status": o.status,
        }
        for o in obligations[:limit]
    ]


DEFAULT_TOOLS: dict[str, Any] = {
    "list_open_requisitions": list_open_requisitions,
    "search_suppliers": search_suppliers,
    "list_expiring_contracts": list_expiring_contracts,
    "list_open_sourcing_events": list_open_sourcing_events,
    "get_spend_summary": get_spend_summary,
    "list_my_pending_tasks": list_my_pending_tasks,
    "search_metadata_objects": search_metadata_objects,
    "list_recent_documents": list_recent_documents,
    "get_operations_report": get_operations_report,
    "list_recent_receipts": list_recent_receipts,
    "list_supplier_risk_flags": list_supplier_risk_flags,
    "list_contract_templates": list_contract_templates,
    "list_overdue_contract_obligations": list_overdue_contract_obligations,
}


def register_default_tools(tool_registry: Any) -> None:
    for name, fn in DEFAULT_TOOLS.items():
        tool_registry.register(name, fn)
