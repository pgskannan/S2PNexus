"""Supplier knowledge graph (HackFW: MADE Challenge, Supplier Relationship Management track).

Builds one connected view of a tenant's supply base from data S2PNexus already
holds, plus the new supplier_certifications table:

    supplier --SUPPLIES--> commodity        (from the tenant's PO line items)
    supplier --HOLDS--> certification       (supplier_certifications, status derived)
    supplier --HAS_OPEN_PO--> purchase order (open POs only)
    purchase order --BILLED_BY--> invoice    (open invoices only, with due date)
    supplier --PARENT_OF--> supplier         (supplier hierarchy)

and answers the question the track brief is about in a single call
(find_certified_sources): "which certified supplier can ship this part, what
is open with them right now, and when do they get paid?"

Nothing here is a separate graph database: the graph is assembled per request
from the relational tables, so it is always as live as the order state.

Tenant isolation: suppliers, commodity codes and NULL-tenant certifications
are shared master data. Everything transactional (POs, invoices, tenant-owned
certifications, preferred/qualification records) is filtered to the caller's
tenant -- PurchaseOrder via its requisition (it has no tenant_id column of its
own, same join as crud.procurement.get_purchase_orders), invoices via their own
tenant_id. As elsewhere in the codebase, tenant_id=None means "no tenant
filter" (single-tenant/legacy users).
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commodity import CommodityCode
from app.models.preferred_supplier import PreferredSupplierStatus
from app.models.procurement import ProcurementInvoice, ProcurementRequisition, PurchaseOrder
from app.models.supplier import Supplier
from app.models.supplier_certification import SupplierCertification
from app.models.supplier_qualification import SupplierQualification

# PO.status values that mean "nothing live with the supplier any more".
CLOSED_PO_STATUSES = frozenset({"draft", "pending_approval", "rejected", "cancelled", "closed", "completed"})
# Invoice.status values that mean "no money still owed / nothing to act on".
CLOSED_INVOICE_STATUSES = frozenset({"paid", "cancelled", "rejected", "void"})
OPEN_EXCEPTION_STATUSES = frozenset({"open"})
EXPIRING_WINDOW_DAYS = 60
MAX_SUPPLIERS = 300

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Small pure helpers (unit-tested directly)
# ---------------------------------------------------------------------------


def normalize_cert_type(value: str) -> str:
    """'ISO 9001' / 'iso-9001' / 'ISO9001' all compare equal."""
    return re.sub(r"[\s\-_:.]+", "", (value or "").casefold())


def certification_status(expires_on: date | None, today: date) -> str:
    if expires_on is None:
        return "valid"
    if expires_on < today:
        return "expired"
    if expires_on <= today + timedelta(days=EXPIRING_WINDOW_DAYS):
        return "expiring"
    return "valid"


def payment_term_days(terms: str | None) -> int | None:
    """Parse the common payment-terms spellings into net days.

    'Net 30' -> 30, 'NET45' -> 45, '2/10 Net 30' -> 30, '60 days' -> 60,
    'Due on receipt' / 'Immediate' -> 0. Unknown -> None.
    """
    if not terms:
        return None
    t = terms.casefold()
    m = re.search(r"net\s*(\d{1,3})", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,3})\s*days?", t)
    if m:
        return int(m.group(1))
    if "receipt" in t or "immediate" in t:
        return 0
    return None


def _money(value: Decimal | None) -> float:
    return float(value or ZERO)


def _po_value(po: PurchaseOrder) -> Decimal:
    for v in (po.grand_total, po.total_amount, po.subtotal):
        if v is not None:
            return Decimal(v)
    return sum((Decimal(li.line_total or 0) for li in (po.line_items or [])), ZERO)


def _invoice_value(inv: ProcurementInvoice) -> Decimal:
    return Decimal(inv.total_amount if inv.total_amount is not None else inv.amount or 0)


def _as_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _commodity_matches(query: str, code: str | None, titles: Iterable[str | None]) -> bool:
    q = query.strip().casefold()
    if not q:
        return True
    if q.isdigit():
        return bool(code) and code.startswith(q)
    return any(q in (t or "").casefold() for t in titles) or (bool(code) and q in code.casefold())


# ---------------------------------------------------------------------------
# Loaders (each one query, tenant-scoped)
# ---------------------------------------------------------------------------


async def _load_open_and_historic_pos(db: AsyncSession, tenant_id: uuid.UUID | None) -> list[PurchaseOrder]:
    q = select(PurchaseOrder).where(PurchaseOrder.supplier_id.is_not(None))
    if tenant_id is not None:
        q = q.join(ProcurementRequisition, PurchaseOrder.requisition_id == ProcurementRequisition.id).where(
            ProcurementRequisition.tenant_id == tenant_id
        )
    return list((await db.execute(q)).scalars().unique().all())


async def _load_invoices(db: AsyncSession, tenant_id: uuid.UUID | None) -> list[ProcurementInvoice]:
    q = select(ProcurementInvoice)
    if tenant_id is not None:
        q = q.where(ProcurementInvoice.tenant_id == tenant_id)
    return list((await db.execute(q)).scalars().unique().all())


def _tenant_visible(column, tenant_id: uuid.UUID | None):
    if tenant_id is None:
        return True
    return or_(column.is_(None), column == tenant_id)


async def _load_certifications(
    db: AsyncSession, tenant_id: uuid.UUID | None, supplier_ids: set[uuid.UUID] | None = None
) -> list[SupplierCertification]:
    q = select(SupplierCertification).where(_tenant_visible(SupplierCertification.tenant_id, tenant_id))
    if supplier_ids is not None:
        if not supplier_ids:
            return []
        q = q.where(SupplierCertification.supplier_id.in_(supplier_ids))
    return list((await db.execute(q)).scalars().all())


async def _latest_by_supplier(db: AsyncSession, model, tenant_id: uuid.UUID | None) -> dict[uuid.UUID, Any]:
    q = select(model).where(_tenant_visible(model.tenant_id, tenant_id))
    out: dict[uuid.UUID, Any] = {}
    for row in (await db.execute(q)).scalars().all():
        prev = out.get(row.supplier_id)
        # Prefer the tenant's own row over a shared one, then the newest.
        key = (row.tenant_id is not None, row.updated_at or datetime.min.replace(tzinfo=timezone.utc))
        if prev is None or key > (prev.tenant_id is not None, prev.updated_at or datetime.min.replace(tzinfo=timezone.utc)):
            out[row.supplier_id] = row
    return out


async def _load_commodity_codes(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, CommodityCode]:
    if not ids:
        return {}
    rows = (await db.execute(select(CommodityCode).where(CommodityCode.id.in_(ids)))).scalars().all()
    return {c.id: c for c in rows}


# ---------------------------------------------------------------------------
# Core aggregation shared by the graph and the sourcing query
# ---------------------------------------------------------------------------


class _SupplyBase:
    """Everything the graph and the sources query need, loaded once."""

    def __init__(self) -> None:
        self.suppliers: dict[uuid.UUID, Supplier] = {}
        self.pos_by_supplier: dict[uuid.UUID, list[PurchaseOrder]] = defaultdict(list)
        self.invoices_by_supplier: dict[uuid.UUID, list[ProcurementInvoice]] = defaultdict(list)
        self.certs_by_supplier: dict[uuid.UUID, list[SupplierCertification]] = defaultdict(list)
        # supplier -> commodity key -> {"spend", "lines", "last_unit_price", "last_ordered"}
        self.supply: dict[uuid.UUID, dict[str, dict[str, Any]]] = defaultdict(dict)
        self.commodities: dict[str, dict[str, Any]] = {}
        self.preferred: dict[uuid.UUID, PreferredSupplierStatus] = {}
        self.qualification: dict[uuid.UUID, SupplierQualification] = {}


async def _load_supply_base(db: AsyncSession, tenant_id: uuid.UUID | None) -> _SupplyBase:
    base = _SupplyBase()

    pos = await _load_open_and_historic_pos(db, tenant_id)
    invoices = await _load_invoices(db, tenant_id)

    po_supplier = {po.id: po.supplier_id for po in pos}
    for po in pos:
        base.pos_by_supplier[po.supplier_id].append(po)
    for inv in invoices:
        sid = inv.supplier_id or po_supplier.get(inv.purchase_order_id) or (
            inv.purchase_order.supplier_id if inv.purchase_order is not None else None
        )
        if sid is not None:
            base.invoices_by_supplier[sid].append(inv)

    commodity_ids = {li.commodity_code_id for po in pos for li in (po.line_items or []) if li.commodity_code_id}
    codes = await _load_commodity_codes(db, commodity_ids)

    for po in pos:
        ordered_at = _as_date(po.created_at)
        for li in po.line_items or []:
            cc = codes.get(li.commodity_code_id) if li.commodity_code_id else None
            if cc is not None:
                key = cc.code
                info = base.commodities.setdefault(
                    key,
                    {
                        "code": cc.code,
                        "title": cc.commodity_title or cc.class_title or cc.family_title or cc.segment_title or cc.code,
                        "titles": [cc.commodity_title, cc.class_title, cc.family_title, cc.segment_title],
                    },
                )
            elif li.commodity_code_free_text:
                key = "text:" + li.commodity_code_free_text.strip().casefold()
                info = base.commodities.setdefault(
                    key, {"code": None, "title": li.commodity_code_free_text.strip(), "titles": [li.commodity_code_free_text]}
                )
            else:
                continue
            edge = base.supply[po.supplier_id].setdefault(
                key, {"spend": ZERO, "lines": 0, "last_unit_price": None, "last_ordered": None, "descriptions": set()}
            )
            edge["spend"] += Decimal(li.line_total or (li.unit_price or 0) * (li.quantity or 0))
            edge["lines"] += 1
            if li.description:
                edge["descriptions"].add(li.description)
            if ordered_at and (edge["last_ordered"] is None or ordered_at >= edge["last_ordered"]):
                edge["last_ordered"] = ordered_at
                edge["last_unit_price"] = li.unit_price

    active_suppliers = (
        await db.execute(
            select(Supplier)
            .where(Supplier.is_active.is_(True), Supplier.lifecycle_status != "offboarded")
            .order_by(Supplier.name)
            .limit(MAX_SUPPLIERS)
        )
    ).scalars().all()
    base.suppliers = {s.id: s for s in active_suppliers}
    # Suppliers the tenant actually trades with always appear, even if
    # deactivated since (their open orders and invoices are still live).
    trading = (set(base.pos_by_supplier) | set(base.invoices_by_supplier)) - set(base.suppliers)
    if trading:
        for s in (await db.execute(select(Supplier).where(Supplier.id.in_(trading)))).scalars().all():
            base.suppliers[s.id] = s

    for cert in await _load_certifications(db, tenant_id, set(base.suppliers)):
        base.certs_by_supplier[cert.supplier_id].append(cert)

    base.preferred = await _latest_by_supplier(db, PreferredSupplierStatus, tenant_id)
    base.qualification = await _latest_by_supplier(db, SupplierQualification, tenant_id)
    return base


def _open_pos(pos: Iterable[PurchaseOrder]) -> list[PurchaseOrder]:
    return [po for po in pos if (po.status or "").casefold() not in CLOSED_PO_STATUSES]


def _open_invoices(invoices: Iterable[ProcurementInvoice]) -> list[ProcurementInvoice]:
    return [inv for inv in invoices if (inv.status or "").casefold() not in CLOSED_INVOICE_STATUSES]


def _invoice_due_date(inv: ProcurementInvoice, supplier: Supplier | None) -> date | None:
    terms = (inv.purchase_order.payment_terms if inv.purchase_order is not None else None) or (
        supplier.payment_terms if supplier is not None else None
    )
    days = payment_term_days(terms)
    issued = _as_date(inv.created_at)
    if days is None or issued is None:
        return None
    return issued + timedelta(days=days)


def _invoice_summary(inv: ProcurementInvoice, supplier: Supplier | None, today: date) -> dict[str, Any]:
    open_exc = [e for e in (inv.exceptions or []) if (e.resolution_status or "open") in OPEN_EXCEPTION_STATUSES]
    due = _invoice_due_date(inv, supplier)
    return {
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "match_status": inv.match_status,
        "block_status": inv.block_status,
        "amount": _money(_invoice_value(inv)),
        "currency": inv.currency,
        "purchase_order_id": str(inv.purchase_order_id) if inv.purchase_order_id else None,
        "open_exceptions": len(open_exc),
        "due_date": due.isoformat() if due else None,
        "days_until_due": (due - today).days if due else None,
    }


def _po_summary(po: PurchaseOrder) -> dict[str, Any]:
    need_by = [li.need_by_date for li in (po.line_items or []) if li.need_by_date]
    return {
        "id": str(po.id),
        "order_number": po.order_number,
        "status": po.status,
        "acknowledgment_status": po.acknowledgment_status,
        "amount": _money(_po_value(po)),
        "currency": po.currency,
        "payment_terms": po.payment_terms,
        "earliest_need_by": min(need_by).date().isoformat() if need_by else None,
    }


def _cert_summary(cert: SupplierCertification, today: date) -> dict[str, Any]:
    return {
        "id": str(cert.id),
        "cert_type": cert.cert_type,
        "certificate_number": cert.certificate_number,
        "issuing_body": cert.issuing_body,
        "scope": cert.scope,
        "issued_on": cert.issued_on.isoformat() if cert.issued_on else None,
        "expires_on": cert.expires_on.isoformat() if cert.expires_on else None,
        "status": certification_status(cert.expires_on, today),
        "tenant_owned": cert.tenant_id is not None,
    }


def _supplier_summary(base: _SupplyBase, s: Supplier, today: date) -> dict[str, Any]:
    open_pos = _open_pos(base.pos_by_supplier.get(s.id, []))
    open_invs = _open_invoices(base.invoices_by_supplier.get(s.id, []))
    inv_summaries = [_invoice_summary(i, s, today) for i in open_invs]
    certs = [_cert_summary(c, today) for c in base.certs_by_supplier.get(s.id, [])]
    pref = base.preferred.get(s.id)
    qual = base.qualification.get(s.id)
    overdue = [i for i in inv_summaries if i["days_until_due"] is not None and i["days_until_due"] < 0]
    next_due = min((i["due_date"] for i in inv_summaries if i["due_date"]), default=None)
    return {
        "id": str(s.id),
        "name": s.name,
        "lifecycle_status": s.lifecycle_status,
        "is_active": s.is_active,
        "risk_level": s.current_risk_level,
        "risk_score": s.current_risk_score,
        "payment_terms": s.payment_terms,
        "preferred_payment_method": s.preferred_payment_method,
        "preferred_status": pref.preferred_status if pref else None,
        "qualification_grade": qual.grade if qual else None,
        "qualification_status": qual.status if qual else None,
        "certifications": certs,
        "valid_certifications": sum(1 for c in certs if c["status"] in ("valid", "expiring")),
        "expiring_certifications": sum(1 for c in certs if c["status"] == "expiring"),
        "expired_certifications": sum(1 for c in certs if c["status"] == "expired"),
        "open_po_count": len(open_pos),
        "open_po_value": round(sum(_money(_po_value(p)) for p in open_pos), 2),
        "open_invoice_count": len(open_invs),
        "open_invoice_value": round(sum(i["amount"] for i in inv_summaries), 2),
        "open_exceptions": sum(i["open_exceptions"] for i in inv_summaries),
        "overdue_invoices": len(overdue),
        "next_payment_due": next_due,
        "commodity_count": len(base.supply.get(s.id, {})),
        "parent_supplier_id": str(s.parent_supplier_id) if s.parent_supplier_id else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def build_supplier_graph(
    db: AsyncSession,
    tenant_id: uuid.UUID | None,
    *,
    supplier_id: uuid.UUID | None = None,
    commodity: str | None = None,
    cert_type: str | None = None,
    include_documents: bool = True,
    today: date | None = None,
) -> dict[str, Any]:
    """Return {nodes, edges, stats} for the tenant's supply base.

    Filters narrow which suppliers are in the graph:
      supplier_id -- that supplier, plus every other supplier that supplies one
                     of the same commodities (its alternate sources).
      commodity   -- suppliers that have supplied a matching commodity (UNSPSC
                     prefix like '3110' or a title substring like 'fastener').
      cert_type   -- suppliers holding a non-expired certificate of that type.
    """
    today = today or date.today()
    base = await _load_supply_base(db, tenant_id)

    selected: set[uuid.UUID] = set(base.suppliers)
    if supplier_id is not None:
        own = set(base.supply.get(supplier_id, {}))
        selected = {supplier_id} | {sid for sid, comms in base.supply.items() if own & set(comms)}
        selected &= set(base.suppliers) | {supplier_id}
    if commodity:
        matching = {k for k, info in base.commodities.items() if _commodity_matches(commodity, info["code"], info["titles"])}
        selected = {sid for sid in selected if matching & set(base.supply.get(sid, {}))}
    if cert_type:
        want = normalize_cert_type(cert_type)
        selected = {
            sid
            for sid in selected
            if any(
                normalize_cert_type(c.cert_type) == want and certification_status(c.expires_on, today) != "expired"
                for c in base.certs_by_supplier.get(sid, [])
            )
        }
    selected = {sid for sid in selected if sid in base.suppliers}

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, node_type: str, label: str, data: dict[str, Any]) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": node_type, "label": label, "data": data}

    for sid in sorted(selected, key=lambda x: base.suppliers[x].name.casefold()):
        s = base.suppliers[sid]
        summary = _supplier_summary(base, s, today)
        sup_node = f"supplier:{sid}"
        add_node(sup_node, "supplier", s.name, summary)

        for key, edge in base.supply.get(sid, {}).items():
            info = base.commodities[key]
            if commodity and not _commodity_matches(commodity, info["code"], info["titles"]):
                continue
            com_node = f"commodity:{key}"
            add_node(com_node, "commodity", info["title"], {"code": info["code"], "title": info["title"]})
            edges.append(
                {
                    "id": f"{sup_node}->{com_node}",
                    "source": sup_node,
                    "target": com_node,
                    "type": "SUPPLIES",
                    "data": {
                        "spend": round(_money(edge["spend"]), 2),
                        "lines": edge["lines"],
                        "last_unit_price": _money(edge["last_unit_price"]) if edge["last_unit_price"] is not None else None,
                        "last_ordered": edge["last_ordered"].isoformat() if edge["last_ordered"] else None,
                        "parts": sorted(edge["descriptions"])[:10],
                    },
                }
            )

        for cert in base.certs_by_supplier.get(sid, []):
            cert_node = f"certification:{normalize_cert_type(cert.cert_type)}"
            add_node(cert_node, "certification", cert.cert_type, {"cert_type": cert.cert_type})
            edges.append(
                {
                    "id": f"{sup_node}->{cert_node}:{cert.id}",
                    "source": sup_node,
                    "target": cert_node,
                    "type": "HOLDS",
                    "data": _cert_summary(cert, today),
                }
            )

        if s.parent_supplier_id and s.parent_supplier_id in selected:
            edges.append(
                {
                    "id": f"supplier:{s.parent_supplier_id}->{sup_node}",
                    "source": f"supplier:{s.parent_supplier_id}",
                    "target": sup_node,
                    "type": "PARENT_OF",
                    "data": {"relationship_type": s.relationship_type},
                }
            )

        if include_documents:
            open_invs = _open_invoices(base.invoices_by_supplier.get(sid, []))
            for po in _open_pos(base.pos_by_supplier.get(sid, [])):
                po_node = f"purchase_order:{po.id}"
                add_node(po_node, "purchase_order", po.order_number, _po_summary(po))
                edges.append({"id": f"{sup_node}->{po_node}", "source": sup_node, "target": po_node, "type": "HAS_OPEN_PO", "data": {}})
            for inv in open_invs:
                inv_node = f"invoice:{inv.id}"
                add_node(inv_node, "invoice", inv.invoice_number, _invoice_summary(inv, s, today))
                parent = f"purchase_order:{inv.purchase_order_id}" if inv.purchase_order_id else None
                if parent not in nodes:
                    # PO already closed (or none): hang the invoice off the supplier.
                    parent = sup_node
                edges.append({"id": f"{parent}->{inv_node}", "source": parent, "target": inv_node, "type": "BILLED_BY", "data": {}})

    supplier_nodes = [n for n in nodes.values() if n["type"] == "supplier"]
    stats = {
        "suppliers": len(supplier_nodes),
        "commodities": sum(1 for n in nodes.values() if n["type"] == "commodity"),
        "certification_types": sum(1 for n in nodes.values() if n["type"] == "certification"),
        "open_purchase_orders": sum(n["data"]["open_po_count"] for n in supplier_nodes),
        "open_po_value": round(sum(n["data"]["open_po_value"] for n in supplier_nodes), 2),
        "open_invoices": sum(n["data"]["open_invoice_count"] for n in supplier_nodes),
        "open_invoice_value": round(sum(n["data"]["open_invoice_value"] for n in supplier_nodes), 2),
        "open_exceptions": sum(n["data"]["open_exceptions"] for n in supplier_nodes),
        "expiring_certifications": sum(n["data"]["expiring_certifications"] for n in supplier_nodes),
        "expired_certifications": sum(n["data"]["expired_certifications"] for n in supplier_nodes),
        "single_source_commodities": sum(
            1
            for n in nodes.values()
            if n["type"] == "commodity" and sum(1 for e in edges if e["type"] == "SUPPLIES" and e["target"] == n["id"]) == 1
        ),
    }
    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": stats,
        "filters": {
            "supplier_id": str(supplier_id) if supplier_id else None,
            "commodity": commodity,
            "cert_type": cert_type,
            "include_documents": include_documents,
        },
        "as_of": today.isoformat(),
    }


async def find_certified_sources(
    db: AsyncSession,
    tenant_id: uuid.UUID | None,
    *,
    commodity: str,
    cert_type: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Answer "who can ship this part, certified, what's open, when are they paid?".

    Candidates are suppliers with purchase history for a matching commodity.
    Each candidate carries its certificate standing for cert_type (if given),
    open POs/invoices with due dates, and last price. Ranked: certificate OK
    first, then preferred status, then fewer open exceptions, lower risk, and
    more history.
    """
    today = today or date.today()
    base = await _load_supply_base(db, tenant_id)
    matching = {k for k, info in base.commodities.items() if _commodity_matches(commodity, info["code"], info["titles"])}
    want = normalize_cert_type(cert_type) if cert_type else None

    preferred_rank = {"strategic": 0, "preferred": 1, "approved": 2, "none": 3, "blocked": 5}
    risk_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    results = []
    for sid, comms in base.supply.items():
        hits = matching & set(comms)
        if not hits or sid not in base.suppliers:
            continue
        s = base.suppliers[sid]
        summary = _supplier_summary(base, s, today)
        if want:
            certs = [c for c in summary["certifications"] if normalize_cert_type(c["cert_type"]) == want]
            best = next((c for c in certs if c["status"] == "valid"), None) or next(
                (c for c in certs if c["status"] == "expiring"), None
            ) or (certs[0] if certs else None)
            cert_standing = best["status"] if best else "missing"
        else:
            best, cert_standing = None, "not_required"
        spend = sum(comms[k]["spend"] for k in hits)
        lines = sum(comms[k]["lines"] for k in hits)
        last = max((comms[k] for k in hits), key=lambda e: e["last_ordered"] or date.min)
        open_invs = [_invoice_summary(i, s, today) for i in _open_invoices(base.invoices_by_supplier.get(sid, []))]
        results.append(
            {
                "supplier": {k: summary[k] for k in summary if k != "certifications"},
                "certification": best,
                "certification_standing": cert_standing,
                "eligible": cert_standing in ("valid", "expiring", "not_required")
                and s.lifecycle_status not in ("offboarding", "offboarded")
                and (summary["preferred_status"] or "").casefold() != "blocked",
                "matched_commodities": [
                    {"key": k, "code": base.commodities[k]["code"], "title": base.commodities[k]["title"]} for k in sorted(hits)
                ],
                "history": {
                    "spend": round(_money(spend), 2),
                    "lines": lines,
                    "last_unit_price": _money(last["last_unit_price"]) if last["last_unit_price"] is not None else None,
                    "last_ordered": last["last_ordered"].isoformat() if last["last_ordered"] else None,
                },
                "open_purchase_orders": [_po_summary(p) for p in _open_pos(base.pos_by_supplier.get(sid, []))],
                "open_invoices": sorted(open_invs, key=lambda i: i["due_date"] or "9999"),
            }
        )

    results.sort(
        key=lambda r: (
            not r["eligible"],
            {"valid": 0, "not_required": 0, "expiring": 1, "expired": 2, "missing": 3}[r["certification_standing"]],
            preferred_rank.get((r["supplier"]["preferred_status"] or "").casefold(), 4),
            r["supplier"]["open_exceptions"],
            risk_rank.get((r["supplier"]["risk_level"] or "").casefold(), 2),
            -r["history"]["spend"],
        )
    )
    return {
        "commodity": commodity,
        "cert_type": cert_type,
        "matched_commodities": [
            {"key": k, "code": base.commodities[k]["code"], "title": base.commodities[k]["title"]} for k in sorted(matching)
        ],
        "eligible_count": sum(1 for r in results if r["eligible"]),
        "sources": results,
        "as_of": today.isoformat(),
    }
