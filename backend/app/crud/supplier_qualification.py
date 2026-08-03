"""CRUD for the SupplierQualification placeholder (Template Framework Phase 2).

See models/supplier_qualification.py -- this is a manual stand-in for the
future template-driven qualification module, kept deliberately small: one
current record per supplier, upserted, grade derived from score via the
shared spec Section 7 bands (single grading authority, no second copy).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_qualification import QUALIFICATION_STATUSES, SupplierQualification
from app.schemas.supplier import SupplierQualificationUpsert
from app.services.template_engine import grade_for_score


async def get_supplier_qualification(
    db: AsyncSession,
    supplier_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> Optional[SupplierQualification]:
    query = select(SupplierQualification).where(SupplierQualification.supplier_id == supplier_id)
    if tenant_id is not None:
        query = query.where(
            (SupplierQualification.tenant_id == tenant_id)
            | (SupplierQualification.tenant_id.is_(None))
        )
    return (await db.execute(query)).scalar_one_or_none()


async def upsert_supplier_qualification(
    db: AsyncSession,
    supplier_id: UUID,
    payload: SupplierQualificationUpsert,
    *,
    actor_id: UUID,
    tenant_id: Optional[UUID] = None,
) -> SupplierQualification:
    if payload.status not in QUALIFICATION_STATUSES:
        raise ValueError(f"Invalid qualification status {payload.status!r}; expected one of {QUALIFICATION_STATUSES}")

    qualification = await get_supplier_qualification(db, supplier_id, tenant_id=tenant_id)
    if qualification is None:
        qualification = SupplierQualification(supplier_id=supplier_id, tenant_id=tenant_id, score=0, grade="F")
        db.add(qualification)

    qualification.score = payload.score
    qualification.grade = grade_for_score(Decimal(payload.score))
    qualification.status = payload.status
    qualification.valid_until = payload.valid_until
    qualification.notes = payload.notes
    qualification.updated_by = actor_id

    await db.commit()
    await db.refresh(qualification)
    return qualification
