"""CRUD helpers for line-item accounting splits (Phase 5).

Split amounts are always validated server-side before being committed --
percentage splits for a given (line_item_type, line_item_id) must sum to
exactly 100, amount splits must sum to exactly the line's line_total. Splits
for one line item must be homogeneous (all-percentage or all-amount), not
mixed, since "50% + $10" has no well-defined total without an implicit
conversion the caller didn't ask for.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.accounting_split import LINE_ITEM_TYPES, SPLIT_METHODS, LineItemAccountingSplit

_HUNDRED = Decimal("100.00")


def _validate_splits(splits: list[dict[str, Any]], line_total: Optional[Decimal]) -> None:
    if not splits:
        raise ValueError("At least one split is required")

    methods = {s.get("split_method") for s in splits}
    if len(methods) > 1:
        raise ValueError("Splits for a single line item must all use the same split_method (percentage or amount)")
    method = methods.pop()
    if method not in SPLIT_METHODS:
        raise ValueError(f"split_method must be one of {SPLIT_METHODS}")

    for s in splits:
        if not s.get("gl_account_code"):
            raise ValueError("Each split requires a gl_account_code")

    if method == "percentage":
        total = sum((Decimal(str(s.get("percentage") or "0")) for s in splits), Decimal("0.00"))
        if total != _HUNDRED:
            raise ValueError(f"Percentage splits must sum to exactly 100, got {total}")
    else:
        if line_total is None:
            raise ValueError("line_total is required to validate amount splits")
        total = sum((Decimal(str(s.get("amount") or "0")) for s in splits), Decimal("0.00"))
        if total != Decimal(str(line_total)):
            raise ValueError(f"Amount splits must sum to exactly the line total ({line_total}), got {total}")


async def get_line_item_splits(
    db: AsyncSession, line_item_type: str, line_item_id: UUID
) -> list[LineItemAccountingSplit]:
    result = await db.execute(
        select(LineItemAccountingSplit).where(
            LineItemAccountingSplit.line_item_type == line_item_type,
            LineItemAccountingSplit.line_item_id == line_item_id,
        )
    )
    return list(result.scalars().all())


async def set_line_item_splits(
    db: AsyncSession,
    line_item_type: str,
    line_item_id: UUID,
    splits: list[dict[str, Any]],
    line_total: Optional[Decimal],
    *,
    commit: bool = True,
) -> list[LineItemAccountingSplit]:
    if line_item_type not in LINE_ITEM_TYPES:
        raise ValueError(f"line_item_type must be one of {LINE_ITEM_TYPES}")

    _validate_splits(splits, line_total)

    existing = await get_line_item_splits(db, line_item_type, line_item_id)
    for row in existing:
        await db.delete(row)
    await db.flush()

    created = []
    for s in splits:
        row = LineItemAccountingSplit(
            line_item_type=line_item_type,
            line_item_id=line_item_id,
            split_method=s["split_method"],
            percentage=s.get("percentage"),
            amount=s.get("amount"),
            gl_account_code=s["gl_account_code"],
            cost_center=s.get("cost_center"),
            department=s.get("department"),
            project_code=s.get("project_code"),
        )
        db.add(row)
        created.append(row)

    await db.flush()
    if commit:
        await db.commit()
        for row in created:
            await db.refresh(row)
    return created


async def ensure_default_split(
    db: AsyncSession,
    line_item_type: str,
    line_item_id: UUID,
    gl_account_code: Optional[str],
    line_total: Optional[Decimal],
    *,
    commit: bool = True,
) -> None:
    """If this line item has no splits yet and we have a GL account to point at,
    create a single 100% / full-amount split row for it. Every line item should
    always have at least one split row so budget/reporting logic never needs an
    "un-split" special case -- but we can only do that if a GL account is actually
    known (e.g. a memo invoice line with no PO link and no resolved account has
    nothing sensible to default to, so it's left with no split rows)."""
    if not gl_account_code:
        return
    existing = await get_line_item_splits(db, line_item_type, line_item_id)
    if existing:
        return
    await set_line_item_splits(
        db,
        line_item_type,
        line_item_id,
        [{"split_method": "amount", "amount": line_total or Decimal("0.00"), "gl_account_code": gl_account_code}],
        line_total,
        commit=commit,
    )


async def copy_splits(
    db: AsyncSession,
    from_type: str,
    from_id: UUID,
    to_type: str,
    to_id: UUID,
    *,
    commit: bool = True,
) -> list[LineItemAccountingSplit]:
    """Copy the source line item's splits as the starting splits for the target
    line item (used for requisition-line -> PO-line and PO-line -> invoice-line
    carry-through). No-op if the source has no splits."""
    source_splits = await get_line_item_splits(db, from_type, from_id)
    if not source_splits:
        return []

    created = []
    for s in source_splits:
        row = LineItemAccountingSplit(
            line_item_type=to_type,
            line_item_id=to_id,
            split_method=s.split_method,
            percentage=s.percentage,
            amount=s.amount,
            gl_account_code=s.gl_account_code,
            cost_center=s.cost_center,
            department=s.department,
            project_code=s.project_code,
        )
        db.add(row)
        created.append(row)

    await db.flush()
    if commit:
        await db.commit()
        for row in created:
            await db.refresh(row)
    return created
