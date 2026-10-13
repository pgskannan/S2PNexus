# Tests for the HackFW supplier knowledge graph: app.services.supplier_graph
# and app.routers.supplier_graph (certifications CRUD + graph/sources endpoints).

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.database.database import Base, get_db
from app.main import app
from app.models.commodity import CommodityCode
from app.models.preferred_supplier import PreferredSupplierStatus
from app.models.procurement import (
    InvoiceMatchException,
    ProcurementInvoice,
    ProcurementRequisition,
    PurchaseOrder,
    PurchaseOrderLineItem,
)
from app.models.supplier import Supplier
from app.models.supplier_certification import SupplierCertification
from app.models.user import User, UserRole
from app.services.supplier_graph import (
    build_supplier_graph,
    certification_status,
    find_certified_sources,
    normalize_cert_type,
    payment_term_days,
)

TODAY = date(2026, 10, 13)


async def _new_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        tables = [t for t in Base.metadata.sorted_tables if t.name != "chat_messages"]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory()


async def _close(engine, db):
    await db.close()
    await engine.dispose()


async def _user(db, *, role=UserRole.PROCUREMENT_MANAGER, tenant_id=None, superuser=False) -> User:
    u = User(
        email=f"{uuid4()}@example.com",
        full_name="Test User",
        hashed_password="not-a-real-hash",
        role=role,
        is_active=True,
        is_superuser=superuser,
        tenant_id=tenant_id,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed(db):
    """Two tenants, three suppliers, one fastener commodity, one extra commodity.

    Tenant A buys fasteners from Acme (AS9100D valid) and Bolt Co (AS9100D
    expired), and has an open invoice with an open price exception at Acme.
    Tenant B buys the same fasteners from Gamma -- tenant A must never see it.
    """
    tenant_a, tenant_b = uuid4(), uuid4()
    user_a = await _user(db, tenant_id=tenant_a)
    user_b = await _user(db, tenant_id=tenant_b)

    fasteners = CommodityCode(
        code="31161500", segment_code="31", segment_title="Manufacturing Components and Supplies",
        family_code="3116", family_title="Hardware", class_code="311615", class_title="Screws",
        commodity_title="Screws",
    )
    bearings = CommodityCode(
        code="31171500", segment_code="31", segment_title="Manufacturing Components and Supplies",
        family_code="3117", family_title="Bearings and bushings and wheels and gears", class_code="311715",
        class_title="Bearings", commodity_title="Bearings",
    )
    db.add_all([fasteners, bearings])

    acme = Supplier(name="Acme Precision", created_by=user_a.id, payment_terms="Net 30", current_risk_level="low")
    bolt = Supplier(name="Bolt Co", created_by=user_a.id, payment_terms="Net 45", current_risk_level="medium")
    gamma = Supplier(name="Gamma Industrial", created_by=user_b.id, payment_terms="Net 15")
    idle = Supplier(name="Idle Supplier", created_by=user_a.id)
    db.add_all([acme, bolt, gamma, idle])
    await db.commit()

    db.add_all([
        SupplierCertification(supplier_id=acme.id, cert_type="AS9100D", expires_on=TODAY + timedelta(days=300)),
        SupplierCertification(supplier_id=acme.id, cert_type="ISO 9001", expires_on=TODAY + timedelta(days=20)),
        SupplierCertification(supplier_id=bolt.id, cert_type="AS9100D", expires_on=TODAY - timedelta(days=5)),
        # Tenant B privately verified something about Acme: invisible to tenant A.
        SupplierCertification(supplier_id=acme.id, cert_type="ITAR", tenant_id=tenant_b),
        PreferredSupplierStatus(supplier_id=acme.id, preferred_status="preferred", tenant_id=tenant_a),
    ])

    async def po(tenant, user, supplier, number, status, commodity, price, created):
        req = ProcurementRequisition(title=f"Req {number}", requested_by=user.id, tenant_id=tenant)
        db.add(req)
        await db.commit()
        p = PurchaseOrder(
            requisition_id=req.id, supplier_id=supplier.id, order_number=number, status=status,
            grand_total=Decimal(price) * 10, created_by=user.id, payment_terms=supplier.payment_terms,
            created_at=created,
        )
        db.add(p)
        await db.commit()
        db.add(PurchaseOrderLineItem(
            purchase_order_id=p.id, line_number=1, description=f"M6 hex screw ({number})",
            commodity_code_id=commodity.id, quantity=Decimal("10"), unit_price=Decimal(price),
            line_total=Decimal(price) * 10,
        ))
        await db.commit()
        return p

    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    po_acme_open = await po(tenant_a, user_a, acme, "PO-A1", "ordered", fasteners, "2.50", t0)
    await po(tenant_a, user_a, acme, "PO-A0", "closed", fasteners, "2.40", t0 - timedelta(days=60))
    await po(tenant_a, user_a, acme, "PO-A2", "ordered", bearings, "12.00", t0)
    await po(tenant_a, user_a, bolt, "PO-B1", "closed", fasteners, "2.10", t0 - timedelta(days=30))
    po_gamma = await po(tenant_b, user_b, gamma, "PO-G1", "ordered", fasteners, "1.90", t0)

    inv_a = ProcurementInvoice(
        invoice_number="INV-A1", tenant_id=tenant_a, supplier_id=acme.id, purchase_order_id=po_acme_open.id,
        amount=Decimal("26.00"), status="pending", match_status="exception", created_by=user_a.id,
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    inv_paid = ProcurementInvoice(
        invoice_number="INV-A0", tenant_id=tenant_a, supplier_id=acme.id, amount=Decimal("24.00"),
        status="paid", created_by=user_a.id,
    )
    inv_g = ProcurementInvoice(
        invoice_number="INV-G1", tenant_id=tenant_b, supplier_id=gamma.id, purchase_order_id=po_gamma.id,
        amount=Decimal("19.00"), status="pending", created_by=user_b.id,
    )
    db.add_all([inv_a, inv_paid, inv_g])
    await db.commit()
    db.add(InvoiceMatchException(invoice_id=inv_a.id, exception_type="price_variance", resolution_status="open"))
    await db.commit()
    ids = {
        "tenant_a": tenant_a, "tenant_b": tenant_b, "user_a": user_a.id, "user_b": user_b.id,
        "acme": acme.id, "bolt": bolt.id, "gamma": gamma.id, "idle": idle.id,
    }
    # Make every service call below load fresh rows, as it would per request.
    db.expire_all()
    return ids


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_payment_term_days_parses_common_spellings():
    assert payment_term_days("Net 30") == 30
    assert payment_term_days("NET45") == 45
    assert payment_term_days("2/10 Net 30") == 30
    assert payment_term_days("60 days") == 60
    assert payment_term_days("Due on receipt") == 0
    assert payment_term_days("whenever") is None
    assert payment_term_days(None) is None


def test_certification_status_and_type_normalization():
    assert certification_status(None, TODAY) == "valid"
    assert certification_status(TODAY - timedelta(days=1), TODAY) == "expired"
    assert certification_status(TODAY + timedelta(days=30), TODAY) == "expiring"
    assert certification_status(TODAY + timedelta(days=200), TODAY) == "valid"
    assert normalize_cert_type("ISO 9001") == normalize_cert_type("iso-9001") == normalize_cert_type("ISO9001")


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def test_graph_is_tenant_scoped_and_carries_live_order_state():
    async def run():
        engine, db = await _new_session()
        try:
            s = await _seed(db)
            g = await build_supplier_graph(db, s["tenant_a"], today=TODAY)
            nodes = {n["id"]: n for n in g["nodes"]}

            acme = nodes[f"supplier:{s['acme']}"]
            assert acme["data"]["open_po_count"] == 2  # PO-A1 + PO-A2, closed PO-A0 excluded
            assert acme["data"]["open_invoice_count"] == 1  # paid INV-A0 excluded
            assert acme["data"]["open_exceptions"] == 1
            assert acme["data"]["preferred_status"] == "preferred"
            # Net 30 from 2026-10-01
            assert acme["data"]["next_payment_due"] == "2026-10-31"

            # Tenant B's private ITAR cert on Acme is not visible to tenant A.
            assert "certification:itar" not in nodes
            assert {c["cert_type"] for c in acme["data"]["certifications"]} == {"AS9100D", "ISO 9001"}

            # Tenant B's order and invoice never appear; Gamma has no tenant-A activity.
            labels = {n["label"] for n in g["nodes"]}
            assert "PO-G1" not in labels and "INV-G1" not in labels
            gamma = nodes[f"supplier:{s['gamma']}"]
            assert gamma["data"]["open_po_count"] == 0 and gamma["data"]["commodity_count"] == 0

            # Edges: Acme and Bolt both supply screws; Bolt's AS9100D is expired.
            supplies = [e for e in g["edges"] if e["type"] == "SUPPLIES" and e["target"] == "commodity:31161500"]
            assert {e["source"] for e in supplies} == {f"supplier:{s['acme']}", f"supplier:{s['bolt']}"}
            bolt_cert = next(e for e in g["edges"] if e["type"] == "HOLDS" and e["source"] == f"supplier:{s['bolt']}")
            assert bolt_cert["data"]["status"] == "expired"

            # Open invoice hangs off its open PO.
            inv_node = next(n for n in g["nodes"] if n["label"] == "INV-A1")
            assert inv_node["data"]["due_date"] == "2026-10-31"
            assert any(e["type"] == "BILLED_BY" and e["target"] == inv_node["id"] and e["source"].startswith("purchase_order:") for e in g["edges"])

            assert g["stats"]["expired_certifications"] == 1
            assert g["stats"]["expiring_certifications"] == 1  # Acme ISO 9001, 20 days out
            assert g["stats"]["single_source_commodities"] == 1  # bearings: Acme only
        finally:
            await _close(engine, db)

    asyncio.run(run())


def test_graph_filters_by_cert_commodity_and_supplier():
    async def run():
        engine, db = await _new_session()
        try:
            s = await _seed(db)

            g = await build_supplier_graph(db, s["tenant_a"], cert_type="as9100d", today=TODAY)
            sups = {n["label"] for n in g["nodes"] if n["type"] == "supplier"}
            assert sups == {"Acme Precision"}  # Bolt's is expired

            g = await build_supplier_graph(db, s["tenant_a"], commodity="bearing", include_documents=False, today=TODAY)
            assert {n["label"] for n in g["nodes"] if n["type"] == "supplier"} == {"Acme Precision"}
            assert {n["id"] for n in g["nodes"] if n["type"] == "commodity"} == {"commodity:31171500"}
            assert not [n for n in g["nodes"] if n["type"] in ("purchase_order", "invoice")]

            # Ego view of Bolt shows Acme as an alternate source for screws, not the idle supplier.
            g = await build_supplier_graph(db, s["tenant_a"], supplier_id=s["bolt"], today=TODAY)
            assert {n["label"] for n in g["nodes"] if n["type"] == "supplier"} == {"Bolt Co", "Acme Precision"}
        finally:
            await _close(engine, db)

    asyncio.run(run())


def test_certified_sources_ranks_eligible_supplier_first():
    async def run():
        engine, db = await _new_session()
        try:
            s = await _seed(db)
            r = await find_certified_sources(db, s["tenant_a"], commodity="3116", cert_type="AS 9100D", today=TODAY)
            names = [x["supplier"]["name"] for x in r["sources"]]
            assert names == ["Acme Precision", "Bolt Co"]  # Gamma is tenant B's
            acme, bolt = r["sources"]
            assert acme["eligible"] and acme["certification_standing"] == "valid"
            assert not bolt["eligible"] and bolt["certification_standing"] == "expired"
            assert acme["history"]["last_unit_price"] == 2.5  # most recent order, not the older 2.40
            assert acme["open_invoices"][0]["due_date"] == "2026-10-31"
            assert r["eligible_count"] == 1

            r = await find_certified_sources(db, s["tenant_b"], commodity="screws", today=TODAY)
            assert [x["supplier"]["name"] for x in r["sources"]] == ["Gamma Industrial"]
            assert r["sources"][0]["certification_standing"] == "not_required"
        finally:
            await _close(engine, db)

    asyncio.run(run())


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_certification_endpoints_enforce_roles_and_tenant_isolation():
    async def run():
        engine, db = await _new_session()
        try:
            s = await _seed(db)
            requester = await _user(db, role=UserRole.REQUESTER, tenant_id=s["tenant_a"])
            tok_a = {"Authorization": f"Bearer {create_access_token(s['user_a'])}"}
            tok_b = {"Authorization": f"Bearer {create_access_token(s['user_b'])}"}
            tok_req = {"Authorization": f"Bearer {create_access_token(requester.id)}"}

            async def override_get_db():
                yield db

            # tests/conftest.py installs a session-wide admin user override;
            # this test needs real token-based users, so swap overrides out.
            saved = dict(app.dependency_overrides)
            app.dependency_overrides.clear()
            app.dependency_overrides[get_db] = override_get_db
            try:
                async with AsyncClient(app=app, base_url="http://test") as client:
                    body = {"supplier_id": str(s["bolt"]), "cert_type": "AS9100D", "expires_on": "2028-01-01"}
                    r = await client.post("/api/v1/supplier-certifications", json=body, headers=tok_req)
                    assert r.status_code == 403

                    r = await client.post(
                        "/api/v1/supplier-certifications",
                        json={**body, "issued_on": "2029-01-01"},
                        headers=tok_a,
                    )
                    assert r.status_code == 422  # expires before issued

                    r = await client.post("/api/v1/supplier-certifications", json=body, headers=tok_a)
                    assert r.status_code == 201, r.text
                    new_id = r.json()["id"]
                    assert r.json()["status"] == "valid" and r.json()["tenant_owned"]

                    # Tenant B neither sees nor can delete tenant A's certificate.
                    r = await client.get(f"/api/v1/supplier-certifications?supplier_id={s['bolt']}", headers=tok_b)
                    assert new_id not in {c["id"] for c in r.json()}
                    r = await client.delete(f"/api/v1/supplier-certifications/{new_id}", headers=tok_b)
                    assert r.status_code == 404

                    # With a renewed AS9100D, Bolt is now an eligible source for tenant A.
                    r = await client.get(
                        "/api/v1/supplier-graph/sources", params={"commodity": "3116", "cert_type": "AS9100D"}, headers=tok_a
                    )
                    assert r.status_code == 200
                    assert r.json()["eligible_count"] == 2

                    r = await client.get("/api/v1/supplier-graph", params={"include_documents": "false"}, headers=tok_a)
                    assert r.status_code == 200
                    assert r.json()["stats"]["suppliers"] >= 2

                    r = await client.delete(f"/api/v1/supplier-certifications/{new_id}", headers=tok_a)
                    assert r.status_code == 204
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(saved)
        finally:
            await _close(engine, db)

    asyncio.run(run())


def test_free_text_commodity_codes_are_searchable():
    """PO lines that carry the UNSPSC code as free text (no commodity_code_id)
    must still join the commodity node and match a code search -- this is how
    the live data looked when the graph first shipped (search returned 0)."""

    async def run():
        engine, db = await _new_session()
        try:
            tenant = uuid4()
            user = await _user(db, tenant_id=tenant)
            db.add(CommodityCode(code="43211500", segment_code="43", class_title="Computers", commodity_title="Computers"))
            known = Supplier(name="Known Code Co", created_by=user.id)
            loose = Supplier(name="Loose Code Co", created_by=user.id)
            db.add_all([known, loose])
            await db.commit()
            for sup, text in ((known, "43211500"), (loose, "14111500")):
                req = ProcurementRequisition(title="R", requested_by=user.id, tenant_id=tenant)
                db.add(req)
                await db.commit()
                po = PurchaseOrder(requisition_id=req.id, supplier_id=sup.id, order_number=f"PO-{text}", status="ordered", created_by=user.id)
                db.add(po)
                await db.commit()
                db.add(PurchaseOrderLineItem(purchase_order_id=po.id, line_number=1, description="x",
                                             commodity_code_free_text=text, quantity=Decimal("1"), unit_price=Decimal("5"), line_total=Decimal("5")))
                await db.commit()
            db.expire_all()

            r = await find_certified_sources(db, tenant, commodity="43211500", today=TODAY)
            assert [x["supplier"]["name"] for x in r["sources"]] == ["Known Code Co"]
            assert r["matched_commodities"][0]["title"] == "Computers"  # resolved via code master

            r = await find_certified_sources(db, tenant, commodity="1411", today=TODAY)
            assert [x["supplier"]["name"] for x in r["sources"]] == ["Loose Code Co"]  # unresolved but numeric

            g = await build_supplier_graph(db, tenant, today=TODAY)
            assert {n["id"] for n in g["nodes"] if n["type"] == "commodity"} == {"commodity:43211500", "commodity:14111500"}
        finally:
            await _close(engine, db)

    asyncio.run(run())
