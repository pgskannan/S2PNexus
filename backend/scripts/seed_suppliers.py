#!/usr/bin/env python3
"""Seed a realistic spread of demo suppliers for the P2P UX backlog (Section 2).

The previous seed scripts covered workflow definitions, supplier *types*,
supplier request templates, registration questionnaires, and the approver
matrix — but never created any ``Supplier`` rows. Without suppliers, PO
auto-creation (``app/services/procurement_workflow.py``) has nothing to bind
PRs to, and every demo PR lands in ``lifecycle_status="exception"`` (its
``_po_creation_blockers`` gate blocks PO creation when the supplier has no
email or is inactive).

This script fills that gap: 18 suppliers across the established category /
commodity taxonomy (IT hardware, software, office supplies, professional
services, facilities, equipment, MRO/raw materials, marketing, HR, travel —
the same starter categories seeded by ``app/main.py`` at startup and used by
``CommodityMatchingPolicy``). Every row is ``is_active=True`` with a real
``contact_email`` so approved PRs produce demoable PO flows instead of
exception PRs.

The Supplier model has no category/commodity columns of its own, so the
category/commodity for each supplier is captured in ``description`` using the
existing taxonomy labels, and the industry is reflected via ``naics_code`` —
no new taxonomy is invented.

USAGE
-----
    cd backend
    python -m scripts.seed_suppliers

Safe to re-run: upsert-by-``external_supplier_code`` (falling back to name),
same pattern as the three-way-policy fixture-style upserts used throughout the
test suite. ``created_by`` is pinned to an existing admin/system user; if none
exists yet, a ``seed.admin@example.com`` system user is created first.
"""

from __future__ import annotations

import asyncio
import pkgutil
from uuid import UUID

import app.models as _models_pkg  # noqa: F401,E402

for _model_module in pkgutil.iter_modules(_models_pkg.__path__):
    __import__(f"app.models.{_model_module.name}")

from sqlalchemy import select

from app.core.security import get_password_hash
from app.crud.supplier import get_supplier_by_external_code, get_supplier_by_name
from app.database.database import db_manager
from app.models.supplier import Supplier
from app.models.user import User, UserRole

SYSTEM_EMAIL = "seed.admin@example.com"
SYSTEM_PASSWORD = "Seed!Admin2026"  # local demo only -- rotate before any real deployment

# (external_supplier_code, name, legal_name, naics_code, category label,
#  commodity label, contact_email, payment_terms, preferred_payment_method)
SUPPLIERS = [
    # ---- IT hardware -----------------------------------------------------
    ("SUP-0001", "Northgate Systems", "Northgate Systems Inc.", "334111", "IT Hardware", "Laptops & Workstations",
     "ap@northgatesystems.com", "Net 30", "ach"),
    ("SUP-0002", "Meridian Data Networks", "Meridian Data Networks LLC", "334118", "IT Hardware", "Networking Equipment",
     "invoicing@meridiandata.net", "Net 45", "wire"),
    ("SUP-0003", "Summit Peripherals", "Summit Peripherals Co.", "334118", "IT Hardware", "Monitors & Peripherals",
     "billing@summitperipherals.com", "Net 30", "ach"),
    # ---- Software / SaaS -------------------------------------------------
    ("SUP-0004", "Cloudline Software", "Cloudline Software Inc.", "513210", "Software", "SaaS Licenses",
     "finance@cloudlinesoftware.com", "Net 30", "ach"),
    ("SUP-0005", "Atlas Analytics", "Atlas Analytics Corp.", "513210", "Software", "Data & BI Platforms",
     "accounts@atlasanalytics.io", "Net 30", "ach"),
    # ---- Office supplies -------------------------------------------------
    ("SUP-0006", "BrightDesk Office Supplies", "BrightDesk Supplies Ltd.", "339940", "Office Supplies", "General Office Supplies",
     "orders@brightdesk.com", "Net 15", "ach"),
    ("SUP-0007", "PaperTrail Stationers", "PaperTrail Stationers LLC", "339940", "Office Supplies", "Paper & Print",
     "ap@papertrail.com", "Net 30", "check"),
    # ---- Professional services (consulting) ------------------------------
    ("SUP-0008", "Sterling Advisory Group", "Sterling Advisory Group LLP", "541611", "Consulting", "Management Consulting",
     "billing@sterlingadvisory.com", "Net 45", "ach"),
    ("SUP-0009", "Praxis Consulting Partners", "Praxis Consulting Partners LLC", "541618", "Consulting", "Strategy & Operations",
     "invoices@praxispartners.com", "Net 45", "wire"),
    ("SUP-0010", "BlueCrest Legal", "BlueCrest Legal LLP", "541110", "Consulting", "Legal Services",
     "ap@bluecrestlegal.com", "Net 30", "wire"),
    # ---- Facilities ------------------------------------------------------
    ("SUP-0011", "ClearSpace Facility Services", "ClearSpace Services Inc.", "561720", "Facilities", "Janitorial & Maintenance",
     "accounts@clearspace.com", "Net 30", "ach"),
    ("SUP-0012", "SecureSite Building Management", "SecureSite BM LLC", "561210", "Facilities", "Security & Facilities",
     "billing@securesite.com", "Net 45", "ach"),
    # ---- Equipment & MRO / raw materials ---------------------------------
    ("SUP-0013", "Ironworks Industrial Supply", "Ironworks Industrial Supply Co.", "332710", "Equipment", "Machinery & Tooling",
     "ap@ironworkssupply.com", "Net 30", "wire"),
    ("SUP-0014", "Harbor Materials Group", "Harbor Materials Group Inc.", "331110", "Raw Materials", "Steel & Raw Materials",
     "invoicing@harbormaterials.com", "Net 60", "wire"),
    ("SUP-0015", "Precision MRO Partners", "Precision MRO Partners LLC", "423840", "MRO", "Maintenance, Repair & Operations",
     "accounts@precisionmro.com", "Net 30", "ach"),
    # ---- Marketing / HR / Travel -----------------------------------------
    ("SUP-0016", "Brightline Marketing Studio", "Brightline Marketing LLC", "541810", "Marketing", "Advertising & Creative",
     "billing@brightlinemarketing.com", "Net 30", "ach"),
    ("SUP-0017", "PeopleFirst HR Solutions", "PeopleFirst HR Solutions Inc.", "561311", "HR", "Payroll & HR Services",
     "ap@peoplefirsthr.com", "Net 30", "ach"),
    ("SUP-0018", "WanderPath Travel Services", "WanderPath Travel Ltd.", "561510", "Travel", "Corporate Travel",
     "finance@wanderpath.com", "Net 15", "ach"),
]


async def _get_system_actor(session) -> UUID:
    """Return an existing admin's user id, or create a 'seed.admin' system user."""
    admin = (
        await session.execute(
            select(User)
            .where(User.role == UserRole.ADMINISTRATOR, User.is_active.is_(True))
            .order_by(User.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if admin is not None:
        return admin.id

    existing = (await session.execute(select(User).where(User.email == SYSTEM_EMAIL))).scalar_one_or_none()
    if existing is not None:
        return existing.id

    user = User(
        email=SYSTEM_EMAIL,
        full_name="Seed Admin",
        hashed_password=get_password_hash(SYSTEM_PASSWORD),
        role=UserRole.ADMINISTRATOR,
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    await session.flush()
    return user.id


async def seed_suppliers() -> dict[str, int]:
    """Upsert the demo suppliers. Returns {"created": n, "existing": n}."""
    stats = {"created": 0, "existing": 0}
    async with db_manager.session_factory() as session:
        actor_id = await _get_system_actor(session)

        for external_code, name, legal_name, naics, category, commodity, email, terms, pay_method in SUPPLIERS:
            existing = await get_supplier_by_external_code(session, external_code)
            if existing is None:
                existing = await get_supplier_by_name(session, name)
            if existing is not None:
                stats["existing"] += 1
                continue

            supplier = Supplier(
                name=name,
                legal_name=legal_name,
                description=f"{category} — {commodity}",
                contact_email=email,
                contact_phone="+1-555-0100",  # placeholder local demo number
                address="100 Demo Way, Springfield, US 62701",
                website=f"https://www.{email.split('@')[1]}",
                tax_id=f"TAX-{external_code}",
                naics_code=naics,
                tax_country="US",
                preferred_payment_method=pay_method,
                payment_terms=terms,
                currency="USD",
                w9_on_file=True,
                external_supplier_code=external_code,
                is_active=True,
                lifecycle_status="active",
                created_by=actor_id,
            )
            session.add(supplier)
            stats["created"] += 1

        await session.commit()

        # Confirm the active+email invariant that PO auto-creation relies on.
        count = (
            await session.execute(
                select(Supplier).where(
                    Supplier.is_active.is_(True),
                    Supplier.contact_email.is_not(None),
                )
            )
        ).scalars().all()
        print(f"Suppliers seeded: {stats['created']} created, {stats['existing']} already present; "
              f"{len(count)} active-with-email supplier(s) total.")
    return stats


if __name__ == "__main__":
    asyncio.run(seed_suppliers())
