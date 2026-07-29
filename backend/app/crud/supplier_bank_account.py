"""CRUD helpers for supplier bank accounts."""

from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_bank_account import SupplierBankAccount


def _unmask(value: str | None) -> str | None:
    if value is None:
        return None
    if value.count("•") > 0:
        return None
    return value


def mask_sensitive_value(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "••••"
    return "•" * (len(value) - 4) + value[-4:]


async def list_supplier_bank_accounts(db: AsyncSession, supplier_id: UUID) -> List[SupplierBankAccount]:
    result = await db.execute(select(SupplierBankAccount).where(SupplierBankAccount.supplier_id == supplier_id))
    return list(result.scalars().all())


async def get_supplier_bank_account(db: AsyncSession, supplier_id: UUID, account_id: UUID) -> SupplierBankAccount | None:
    result = await db.execute(
        select(SupplierBankAccount).where(
            SupplierBankAccount.id == account_id,
            SupplierBankAccount.supplier_id == supplier_id,
        )
    )
    return result.scalar_one_or_none()


async def _apply_bank_updates(account: SupplierBankAccount, updates: dict) -> None:
    if "account_number" in updates:
        incoming = updates["account_number"]
        unmasked = _unmask(incoming)
        if unmasked is not None:
            account.account_number = unmasked
    if "iban" in updates:
        incoming = updates["iban"]
        unmasked = _unmask(incoming)
        if unmasked is not None:
            account.iban = unmasked
    for key, value in updates.items():
        if key in {"id", "supplier_id", "updated_by"}:
            continue
        if key in {"account_number", "iban"}:
            continue
        setattr(account, key, value)


async def create_supplier_bank_account(db: AsyncSession, supplier_id: UUID, updated_by: UUID | None, **fields) -> SupplierBankAccount:
    account_number = _unmask(fields.get("account_number"))
    iban = _unmask(fields.get("iban"))
    account = SupplierBankAccount(
        supplier_id=supplier_id,
        updated_by=updated_by,
        **{k: v for k, v in fields.items() if k not in {"id", "supplier_id", "updated_by", "account_number", "iban"}},
    )
    account.account_number = account_number
    account.iban = iban
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def update_supplier_bank_account(db: AsyncSession, supplier_id: UUID, account_id: UUID, updated_by: UUID | None, updates: dict) -> SupplierBankAccount:
    account = await get_supplier_bank_account(db, supplier_id=supplier_id, account_id=account_id)
    if account is None:
        raise ValueError("Bank account not found")
    await _apply_bank_updates(account, updates)
    account.updated_by = updated_by
    await db.commit()
    await db.refresh(account)
    return account


async def delete_supplier_bank_account(db: AsyncSession, supplier_id: UUID, account_id: UUID) -> None:
    account = await get_supplier_bank_account(db, supplier_id=supplier_id, account_id=account_id)
    if account is None:
        raise ValueError("Bank account not found")
    await db.delete(account)
    await db.commit()


async def bulk_upsert_supplier_bank_accounts(db: AsyncSession, rows: list[dict], updated_by: UUID | None) -> int:
    loaded = 0
    for r in rows:
        account = None
        if r.get("id"):
            account = await get_supplier_bank_account(db, supplier_id=r["supplier_id"], account_id=r["id"])
        if account is None:
            account = SupplierBankAccount(
                supplier_id=r["supplier_id"],
                updated_by=updated_by,
                bank_name=r.get("bank_name"),
                account_holder_name=r.get("account_holder_name"),
                account_number=r.get("account_number"),
                iban=r.get("iban"),
                swift_bic=r.get("swift_bic"),
                routing_number=r.get("routing_number"),
                currency=r.get("currency"),
                is_primary=r.get("is_primary", False),
                intermediary_bank_swift=r.get("intermediary_bank_swift"),
            )
            db.add(account)
        else:
            await _apply_bank_updates(account, r)
            account.updated_by = updated_by
        loaded += 1

    await db.commit()
    return loaded


async def count_supplier_bank_accounts(db: AsyncSession, supplier_id: UUID | None = None) -> int:
    stmt = select(SupplierBankAccount)
    if supplier_id is not None:
        stmt = stmt.where(SupplierBankAccount.supplier_id == supplier_id)
    result = await db.execute(stmt)
    return len(result.scalars().all())


async def delete_all_supplier_bank_accounts(db: AsyncSession, supplier_id: UUID | None = None) -> int:
    stmt = delete(SupplierBankAccount)
    if supplier_id is not None:
        stmt = stmt.where(SupplierBankAccount.supplier_id == supplier_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0


async def set_primary_supplier_bank_account(db: AsyncSession, supplier_id: UUID, account_id: UUID) -> SupplierBankAccount:
    account = await get_supplier_bank_account(db, supplier_id=supplier_id, account_id=account_id)
    if account is None:
        raise ValueError("Bank account not found")
    await db.execute(
        update(SupplierBankAccount)
        .where(SupplierBankAccount.supplier_id == supplier_id, SupplierBankAccount.is_primary == True)
        .values(is_primary=False)
    )
    account.is_primary = True
    await db.commit()
    await db.refresh(account)
    return account
