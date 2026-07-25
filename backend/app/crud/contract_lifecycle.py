"""CRUD helpers for Contract Lifecycle extensions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract
from app.models.contract_lifecycle import (
    ContractClause,
    ContractClauseLink,
    ContractObligation,
    ContractRenewal,
    ContractTemplate,
)
from app.schemas.contract_lifecycle import (
    ContractClauseCreate,
    ContractClauseLinkCreate,
    ContractClauseUpdate,
    ContractObligationCreate,
    ContractObligationUpdate,
    ContractRenewalCreate,
    ContractTemplateCreate,
    ContractTemplateUpdate,
)


def _normalize_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# --- Clause library -----------------------------------------------------

async def get_clauses(
    db: AsyncSession, skip: int = 0, limit: int = 100, search: Optional[str] = None, category: Optional[str] = None
) -> list[ContractClause]:
    query = select(ContractClause)
    if category:
        query = query.where(ContractClause.category == category)
    if search:
        query = query.where(ContractClause.title.ilike(f"%{search}%") | ContractClause.clause_text.ilike(f"%{search}%"))
    query = query.order_by(desc(ContractClause.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_clauses_count(db: AsyncSession, search: Optional[str] = None, category: Optional[str] = None) -> int:
    query = select(func.count(ContractClause.id))
    if category:
        query = query.where(ContractClause.category == category)
    if search:
        query = query.where(ContractClause.title.ilike(f"%{search}%") | ContractClause.clause_text.ilike(f"%{search}%"))
    result = await db.execute(query)
    return result.scalar_one()


async def create_clause(db: AsyncSession, clause_in: ContractClauseCreate, created_by: UUID) -> ContractClause:
    clause = ContractClause(**clause_in.model_dump(), created_by=created_by)
    db.add(clause)
    await db.commit()
    await db.refresh(clause)
    return clause


async def get_clause(db: AsyncSession, clause_id: UUID | str) -> Optional[ContractClause]:
    result = await db.execute(select(ContractClause).where(ContractClause.id == _normalize_uuid(clause_id)))
    return result.scalar_one_or_none()


async def update_clause(db: AsyncSession, clause_id: UUID | str, clause_in: ContractClauseUpdate) -> Optional[ContractClause]:
    clause = await get_clause(db, clause_id)
    if not clause:
        return None
    update_data = clause_in.model_dump(exclude_unset=True)
    if update_data:
        clause.version += 1
    for field, value in update_data.items():
        setattr(clause, field, value)
    await db.commit()
    await db.refresh(clause)
    return clause


async def link_clause_to_contract(
    db: AsyncSession, contract_id: UUID | str, link_in: ContractClauseLinkCreate, *, added_by: UUID
) -> ContractClauseLink:
    link = ContractClauseLink(contract_id=_normalize_uuid(contract_id), added_by=added_by, **link_in.model_dump())
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


# --- Template library -----------------------------------------------------

async def get_templates(
    db: AsyncSession, skip: int = 0, limit: int = 100, contract_type: Optional[str] = None, is_active: Optional[bool] = None
) -> list[ContractTemplate]:
    query = select(ContractTemplate)
    if contract_type:
        query = query.where(ContractTemplate.contract_type == contract_type)
    if is_active is not None:
        query = query.where(ContractTemplate.is_active == is_active)
    query = query.order_by(desc(ContractTemplate.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_templates_count(
    db: AsyncSession, contract_type: Optional[str] = None, is_active: Optional[bool] = None
) -> int:
    query = select(func.count(ContractTemplate.id))
    if contract_type:
        query = query.where(ContractTemplate.contract_type == contract_type)
    if is_active is not None:
        query = query.where(ContractTemplate.is_active == is_active)
    result = await db.execute(query)
    return result.scalar_one()


async def create_template(db: AsyncSession, template_in: ContractTemplateCreate, created_by: UUID) -> ContractTemplate:
    template = ContractTemplate(**template_in.model_dump(), created_by=created_by)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


async def get_template(db: AsyncSession, template_id: UUID | str) -> Optional[ContractTemplate]:
    result = await db.execute(select(ContractTemplate).where(ContractTemplate.id == _normalize_uuid(template_id)))
    return result.scalar_one_or_none()


async def update_template(
    db: AsyncSession, template_id: UUID | str, template_in: ContractTemplateUpdate
) -> Optional[ContractTemplate]:
    template = await get_template(db, template_id)
    if not template:
        return None
    update_data = template_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


# --- Obligation tracking -----------------------------------------------------

async def add_obligation(
    db: AsyncSession, contract_id: UUID | str, obligation_in: ContractObligationCreate, *, created_by: UUID
) -> ContractObligation:
    obligation = ContractObligation(contract_id=_normalize_uuid(contract_id), created_by=created_by, **obligation_in.model_dump())
    db.add(obligation)
    await db.commit()
    await db.refresh(obligation)
    return obligation


async def get_obligation(db: AsyncSession, obligation_id: UUID | str) -> Optional[ContractObligation]:
    result = await db.execute(select(ContractObligation).where(ContractObligation.id == _normalize_uuid(obligation_id)))
    return result.scalar_one_or_none()


async def update_obligation(
    db: AsyncSession, obligation_id: UUID | str, obligation_in: ContractObligationUpdate
) -> Optional[ContractObligation]:
    obligation = await get_obligation(db, obligation_id)
    if not obligation:
        return None
    update_data = obligation_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(obligation, field, value)
    if update_data.get("status") == "completed" and obligation.completed_at is None:
        obligation.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(obligation)
    return obligation


async def get_overdue_obligations(db: AsyncSession, as_of: Optional[datetime] = None) -> list[ContractObligation]:
    """Obligations that are still pending past their due date."""
    reference_date = (as_of or datetime.now(timezone.utc)).date()
    query = select(ContractObligation).where(
        ContractObligation.status == "pending",
        ContractObligation.due_date.is_not(None),
        ContractObligation.due_date < reference_date,
    )
    result = await db.execute(query)
    return list(result.scalars().all())


# --- Renewals -----------------------------------------------------

async def renew_contract(
    db: AsyncSession, contract_id: UUID | str, renewal_in: ContractRenewalCreate, *, processed_by: UUID
) -> Optional[Contract]:
    result = await db.execute(select(Contract).where(Contract.id == _normalize_uuid(contract_id)))
    contract = result.scalar_one_or_none()
    if not contract:
        return None

    renewal = ContractRenewal(
        contract_id=contract.id,
        previous_end_date=contract.end_date,
        new_end_date=renewal_in.new_end_date,
        notes=renewal_in.notes,
        processed_by=processed_by,
    )
    db.add(renewal)

    contract.end_date = renewal_in.new_end_date
    contract.status = "active"
    contract.lifecycle_status = "renewed"

    await db.commit()
    await db.refresh(contract)
    return contract
