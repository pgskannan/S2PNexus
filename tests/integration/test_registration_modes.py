"""Integration-style tests for registration_mode branching (FS 5.2 / Phase 2).

Uses in-memory SQLite + real SQLAlchemy models (same pattern as
test_supplier_request_template_routing.py).
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models.supplier import Supplier
from app.models.supplier_registration import SupplierRegistration
from app.models.supplier_request import SupplierRequest
from app.models.supplier_type import SupplierType
from app.models.user import User, UserRole
from app.schemas.supplier_type import SupplierTypeCreate
from app.crud.supplier_type import upsert_supplier_type_by_code
from app.services.registration_trigger import on_supplier_request_approved


async def _setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, Session


async def _seed_user(session: AsyncSession) -> User:
    user = User(
        email=f"creator-{uuid.uuid4().hex[:8]}@s2pnexus-demo.com",
        full_name="Creator",
        hashed_password="x",
        role=UserRole.PROCUREMENT_MANAGER,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_type(session: AsyncSession, code: str, mode: str, modules: list[str]) -> SupplierType:
    return await upsert_supplier_type_by_code(
        session,
        SupplierTypeCreate(
            code=code,
            name=code,
            registration_mode=mode,
            required_questionnaire_modules=modules,
            approval_workflow_config=["BU_MANAGER"],
            ad_hoc_task_templates=[],
            notification_rule={"sla_days": 14, "reminder_at_days": [7], "escalation_at_days": 14},
            is_active=True,
        ),
        commit=False,
    )


async def _make_request(session: AsyncSession, user: User, stype: SupplierType) -> SupplierRequest:
    req = SupplierRequest(
        title=f"Request {stype.code}",
        requestor_id=user.id,
        supplier_type_id=stype.id,
        suggested_supplier_name=f"Vendor {stype.code}",
        status="submitted",
        lifecycle_status="submitted",
        approval_status="pending",
        estimated_annual_spend=Decimal("1000"),
    )
    session.add(req)
    await session.flush()
    return req


@pytest.mark.asyncio
async def test_auto_mode_sends_workbook(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import settings

    settings.UPLOAD_DIR = str(tmp_path)

    engine, Session = await _setup_db()
    async with Session() as session:
        user = await _seed_user(session)
        stype = await _seed_type(session, "STD_VENDOR", "auto", ["core"])
        req = await _make_request(session, user, stype)
        result = await on_supplier_request_approved(session, req.id, actor_id=user.id, commit=False)
        await session.commit()

        assert result["ok"]
        assert result["registration_mode"] == "auto"
        assert result["registration_id"]
        assert result["supplier_id"]

        reg = await session.get(SupplierRegistration, uuid.UUID(result["registration_id"]))
        assert reg is not None
        assert reg.status == "sent"
        assert reg.structure_hash
        assert reg.sent_workbook_path
        supplier = await session.get(Supplier, uuid.UUID(result["supplier_id"]))
        assert supplier is not None
        assert supplier.lifecycle_status == "pending_registration"
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_mode_pending_task(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import settings

    settings.UPLOAD_DIR = str(tmp_path)

    engine, Session = await _setup_db()
    async with Session() as session:
        user = await _seed_user(session)
        stype = await _seed_type(session, "CONSULTANT", "manual", ["core"])
        req = await _make_request(session, user, stype)
        result = await on_supplier_request_approved(session, req.id, actor_id=user.id, commit=False)
        await session.commit()

        assert result["registration_mode"] == "manual"
        reg = await session.get(SupplierRegistration, uuid.UUID(result["registration_id"]))
        assert reg is not None
        assert reg.status == "pending_registration"
        assert reg.workbook_sent_at is None
        assert reg.structure_hash is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_none_mode_skips_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.core.config import settings

    settings.UPLOAD_DIR = str(tmp_path)

    engine, Session = await _setup_db()
    async with Session() as session:
        user = await _seed_user(session)
        stype = await _seed_type(session, "ONE_TIME_VENDOR", "none", [])
        req = await _make_request(session, user, stype)
        result = await on_supplier_request_approved(session, req.id, actor_id=user.id, commit=False)
        await session.commit()

        assert result["registration_mode"] == "none"
        assert result["registration_id"] is None
        supplier = await session.get(Supplier, uuid.UUID(result["supplier_id"]))
        assert supplier is not None
        assert supplier.is_active is True
        assert supplier.lifecycle_status == "active"
        regs = (await session.execute(__import__("sqlalchemy").select(SupplierRegistration))).scalars().all()
        assert len(regs) == 0
    await engine.dispose()
