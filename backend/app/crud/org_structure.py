"""CRUD helpers for organization structure master data: Departments, Cost Centers, Plants."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_structure import Department, CostCenter, Plant
from app.models.document_numbering import NO_TENANT_ID


def _tenant_or_default(tenant_id: Optional[UUID]) -> UUID:
    return tenant_id if tenant_id is not None else NO_TENANT_ID


async def list_departments(db: AsyncSession, tenant_id: Optional[UUID] = None) -> List[Department]:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(Department).where(Department.tenant_id == tid))
    return list(result.scalars().all())


async def get_department_by_code(db: AsyncSession, tenant_id: Optional[UUID], code: str) -> Department | None:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(Department).where(Department.tenant_id == tid, Department.code == code))
    return result.scalar_one_or_none()


async def count_departments(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(Department).where(Department.tenant_id == tid))
    return len(result.scalars().all())


async def delete_all_departments(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    tid = _tenant_or_default(tenant_id)
    stmt = delete(Department).where(Department.tenant_id == tid)
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount or 0


async def bulk_upsert_departments(db: AsyncSession, tenant_id: Optional[UUID], rows: list[dict]) -> int:
    tid = _tenant_or_default(tenant_id)
    # load existing by code
    codes = [r.get("code") for r in rows if r.get("code")]
    existing = {}
    if codes:
        q = await db.execute(select(Department).where(Department.tenant_id == tid, Department.code.in_(codes)))
        for d in q.scalars().all():
            existing[d.code] = d

    loaded = 0
    for r in rows:
        code = r.get("code")
        if not code:
            continue
        dept = existing.get(code)
        if dept is None:
            dept = Department(tenant_id=tid, code=code)
            db.add(dept)
        dept.name = r.get("name") or dept.name
        dept.parent_department_id = r.get("parent_department_id") or dept.parent_department_id
        dept.is_active = r.get("is_active", dept.is_active)
        loaded += 1

    await db.commit()
    return loaded


async def list_cost_centers(db: AsyncSession, tenant_id: Optional[UUID] = None) -> List[CostCenter]:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(CostCenter).where(CostCenter.tenant_id == tid))
    return list(result.scalars().all())


async def get_cost_center_by_code(db: AsyncSession, tenant_id: Optional[UUID], code: str) -> CostCenter | None:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(CostCenter).where(CostCenter.tenant_id == tid, CostCenter.code == code))
    return result.scalar_one_or_none()


async def count_cost_centers(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(CostCenter).where(CostCenter.tenant_id == tid))
    return len(result.scalars().all())


async def delete_all_cost_centers(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    tid = _tenant_or_default(tenant_id)
    stmt = delete(CostCenter).where(CostCenter.tenant_id == tid)
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount or 0


async def bulk_upsert_cost_centers(db: AsyncSession, tenant_id: Optional[UUID], rows: list[dict]) -> int:
    tid = _tenant_or_default(tenant_id)
    codes = [r.get("code") for r in rows if r.get("code")]
    existing = {}
    if codes:
        q = await db.execute(select(CostCenter).where(CostCenter.tenant_id == tid, CostCenter.code.in_(codes)))
        for c in q.scalars().all():
            existing[c.code] = c

    loaded = 0
    for r in rows:
        code = r.get("code")
        if not code:
            continue
        cc = existing.get(code)
        if cc is None:
            cc = CostCenter(tenant_id=tid, code=code)
            db.add(cc)
        cc.name = r.get("name") or cc.name
        cc.department_id = r.get("department_id") or cc.department_id
        cc.is_active = r.get("is_active", cc.is_active)
        loaded += 1

    await db.commit()
    return loaded


async def list_plants(db: AsyncSession, tenant_id: Optional[UUID] = None) -> List[Plant]:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(Plant).where(Plant.tenant_id == tid))
    return list(result.scalars().all())


async def get_plant_by_code(db: AsyncSession, tenant_id: Optional[UUID], code: str) -> Plant | None:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(Plant).where(Plant.tenant_id == tid, Plant.code == code))
    return result.scalar_one_or_none()


async def count_plants(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    tid = _tenant_or_default(tenant_id)
    result = await db.execute(select(Plant).where(Plant.tenant_id == tid))
    return len(result.scalars().all())


async def delete_all_plants(db: AsyncSession, tenant_id: Optional[UUID] = None) -> int:
    tid = _tenant_or_default(tenant_id)
    stmt = delete(Plant).where(Plant.tenant_id == tid)
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount or 0


async def bulk_upsert_plants(db: AsyncSession, tenant_id: Optional[UUID], rows: list[dict]) -> int:
    tid = _tenant_or_default(tenant_id)
    codes = [r.get("code") for r in rows if r.get("code")]
    existing = {}
    if codes:
        q = await db.execute(select(Plant).where(Plant.tenant_id == tid, Plant.code.in_(codes)))
        for p in q.scalars().all():
            existing[p.code] = p

    loaded = 0
    for r in rows:
        code = r.get("code")
        if not code:
            continue
        p = existing.get(code)
        if p is None:
            p = Plant(tenant_id=tid, code=code)
            db.add(p)
        p.name = r.get("name") or p.name
        p.address_line1 = r.get("address_line1") or p.address_line1
        p.address_line2 = r.get("address_line2") or p.address_line2
        p.city = r.get("city") or p.city
        p.state_province = r.get("state_province") or p.state_province
        p.postal_code = r.get("postal_code") or p.postal_code
        p.country = r.get("country") or p.country
        p.tax_id = r.get("tax_id") or p.tax_id
        p.is_active = r.get("is_active", p.is_active)
        loaded += 1

    await db.commit()
    return loaded
