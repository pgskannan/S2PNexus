"""Regression guard for backend/scripts/seed_suppliers.py (backlog Section 2).

Asserts that:
  1. running the seed produces the expected number of demo suppliers,
  2. every seeded supplier satisfies the PO auto-creation invariant
     (``is_active=True`` AND a real ``contact_email``) -- otherwise approved
     PRs land in ``lifecycle_status="exception"`` instead of producing
     demoable PO flows (see ``_po_creation_blockers`` in
     ``app/services/procurement_workflow.py``), and
  3. re-running the script is idempotent (no duplicate rows).

Follows the pattern of tests/unit/test_seed_default_workflows.py: the seed
function opens its own session via ``db_manager.session_factory()``, which is
safe because tests/conftest.py's session-scoped autouse fixture rebinds the
global ``db_manager`` to the same in-memory SQLite test engine ``db_session``
uses.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from sqlalchemy import delete, func, select

from app.models.supplier import Supplier

from scripts.seed_suppliers import SUPPLIERS, seed_suppliers


@pytest.mark.asyncio
async def test_seed_suppliers_creates_demo_spread(db_session):
    # The tests share one in-memory DB with other files, so start clean to
    # keep the count assertions independent of ordering.
    await db_session.execute(delete(Supplier))
    await db_session.commit()

    stats = await seed_suppliers()
    assert stats["created"] == len(SUPPLIERS)

    suppliers = (await db_session.execute(select(Supplier))).scalars().all()
    assert len(suppliers) == len(SUPPLIERS)

    # Every seeded supplier must pass the PO auto-creation gate: active + email.
    for supplier in suppliers:
        assert supplier.is_active is True, f"{supplier.name}: expected active"
        assert supplier.contact_email, f"{supplier.name}: expected contact_email"
        assert supplier.lifecycle_status == "active"
        assert supplier.external_supplier_code, f"{supplier.name}: expected external_supplier_code"

    # A realistic spread across categories/commodities (encoded in description).
    descriptions = " | ".join(s.description or "" for s in suppliers)
    for label in ("IT Hardware", "Software", "Office Supplies", "Consulting", "Facilities", "Raw Materials", "MRO", "Marketing", "HR", "Travel"):
        assert label in descriptions, f"expected a supplier for category/commodity: {label}"


@pytest.mark.asyncio
async def test_seed_suppliers_is_idempotent(db_session):
    # The tests share one in-memory DB, so start from a clean table to keep
    # this test independent of test ordering.
    await db_session.execute(delete(Supplier))
    await db_session.commit()

    first = await seed_suppliers()
    second = await seed_suppliers()

    assert first["created"] == len(SUPPLIERS)
    assert second["created"] == 0
    assert second["existing"] == len(SUPPLIERS)

    total = (await db_session.execute(select(func.count()).select_from(Supplier))).scalar_one()
    assert total == len(SUPPLIERS)
