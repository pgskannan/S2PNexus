# Prompt: Supplier Master Data (gold-standard fields, addresses, banking) + CSV load UI

Copy the whole thing into Copilot (or whichever AI coding tool) in one go — this is a single phase, not a multi-part sequence like the procurement rebuild prompt. No dependency on that other prompt, but it does reuse two things already built and tested in this repo, so point Copilot at them as the reference implementation rather than letting it invent its own shape:

- `app/models/gl_account.py`, `app/crud/gl_account.py`, `app/routers/gl_accounts.py`, `app/services/master_data_import.py`, and the "Master Data" section in `frontend/app/dashboard/settings/page.tsx` — this is the CSV upload/delete-all/count pattern to copy for supplier master data. Same shape: admin-only, upload validates/reports row-level errors instead of silently accepting garbage, delete-all is a full reset per dataset, one Settings card per dataset with a row count.
- `app/models/address.py` / `app/crud/address.py` (Phase 1 address book) — **do not extend this table for supplier addresses.** It's hardcoded to `owner_type in ("user", "tenant")` with `owner_id` FK'd to `users.id`; bolting a third owner type onto it means either loosening that FK (weakens the existing user/tenant address book) or faking a users.id for suppliers. Build a separate `SupplierAddress` table instead — same column shape, different owner semantics (address *type* per supplier, not owner *type*).

---

## Context: codebase conventions (same as every other domain here)

You're working in the S2PNexus backend, FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2, Next.js frontend. Follow these exactly:

1. **Dev order**: model → Pydantic schema → CRUD → router → Alembic migration → tests → a real (non-mocked) smoke test against SQLite.
2. **Tenant scoping**: any tenant-configurable table uses the `NO_TENANT_ID` sentinel from `app.models.document_numbering` (all-`f` UUID, **never all-zero** — that module's docstring explains the SQLite NUMERIC-affinity corruption bug an all-zero sentinel causes) for a global/shared row, with tenant-specific rows taking priority. Suppliers themselves aren't currently tenant-scoped in this codebase (check `app/models/supplier.py` before assuming otherwise) — match whatever the existing `Supplier` model actually does today rather than introducing tenant scoping only on the new tables.
3. **Testing pattern**: this repo's pytest/pytest-asyncio combination breaks on async generator fixtures. Every `tests/integration/*.py` file uses a plain `def test_x(): asyncio.run(run_test())` wrapper with a self-contained in-memory SQLite session helper (`Base.metadata.create_all` excluding the `chat_messages` table, which uses a Postgres-only JSONB column SQLite can't compile) — copy that pattern exactly, don't introduce `@pytest.mark.asyncio`.
4. **Migrations**: there must be exactly one Alembic head before you write a new migration's `down_revision` — check `alembic/versions/` for the current head first (walk `down_revision` links, don't just eyeball filenames), this repo has been bitten by two sessions branching off the same head before.
5. All IDs are `UUID(as_uuid=True)` from `sqlalchemy.dialects.postgresql`; timestamps are `DateTime(timezone=True)`.
6. CSV upload endpoints: reuse `app/services/master_data_import.py`'s pattern (column-alias-tolerant parsing, e.g. accept both `"Bank Name"` and `"bank_name"`; a `MasterDataCSVError` with a list of row-level human-readable errors, never a bare exception) — add new parse functions there rather than a separate module, so the row-level error contract stays consistent everywhere it's used.

---

## Current state (what you're upgrading from)

`app/models/supplier.py`'s `Supplier` model today has: `name`, `description`, `contact_email`, `contact_phone`, a single free-text `address` string, `website`, `tax_id`, `payment_terms`, `currency`, plus lifecycle/hierarchy/merge fields from later phases. There is **no structured address** (no city/state/postal/country fields, no way to have separate legal vs. remit-to vs. shipping addresses), **no banking/payment information at all**, no legal-name-vs-trading-name distinction, no D-U-N-S number, no industry classification, and no supplier diversity/certification data. None of this master data has a CSV import path — it can only be entered one supplier at a time through whatever UI exists today.

---

## What to build

### 1. Extend `Supplier` (`app/models/supplier.py`) with gold-standard header fields

Add nullable columns (don't touch existing ones): `legal_name` (registered legal entity name, may differ from the existing `name` which can stay as the commonly-used/trading name), `duns_number` (String(9)), `naics_code` (String(10) — industry classification), `vat_number` (String(50), separate from the existing `tax_id` since VAT and a domestic tax ID are frequently both needed for international suppliers), `tax_country` (String(2), ISO 3166-1 alpha-2), `preferred_payment_method` (String(20): `"ach"` | `"wire"` | `"check"` | `"card"`), `diversity_classifications` (String array or comma-delimited String(500) — small business, minority-owned, women-owned, veteran-owned, etc.; keep it a simple string field, don't build a separate lookup table for this), `w9_on_file` (Boolean, default False), `external_supplier_code` (String(50), nullable, unique-per-tenant-if-tenant-scoped — the supplier's ID in an external ERP/MDM system, for reconciliation on import; separate from the internal `id` UUID primary key).

### 2. New model `SupplierAddress` (`app/models/supplier_address.py`, new file)

`id`, `supplier_id` (FK `suppliers.id`, `ondelete="CASCADE"` — an address has no meaning without its supplier, unlike the generic user/tenant address book), `address_type` (String(20): `"legal"` | `"remit_to"` | `"shipping"` | `"billing"` — a supplier can have more than one of each type over time, e.g. multiple shipping locations, so this is **not** a one-row-per-type table), `attention_to`, `address_line1`, `address_line2`, `city`, `state_province`, `postal_code`, `country`, `phone`, `is_default` (Boolean — default per `(supplier_id, address_type)` pair, enforce "only one default per type per supplier" in CRUD the same way `Address.is_default` is enforced for users in `crud/address.py`, not just a DB constraint), timestamps. Index `(supplier_id, address_type)`.

### 3. New model `SupplierBankAccount` (`app/models/supplier_bank_account.py`, new file) — **handle as sensitive data**

`id`, `supplier_id` (FK `suppliers.id`, `ondelete="CASCADE"`), `bank_name`, `account_holder_name` (the beneficiary name on the account — often differs slightly from the supplier's legal name), `account_number` (String — see masking note below), `iban` (String(34), nullable — international), `swift_bic` (String(11), nullable), `routing_number` (String(20), nullable — ABA, domestic US), `currency` (String(3), ISO 4217), `is_primary` (Boolean, default False, "only one primary per supplier" enforced in CRUD), `intermediary_bank_swift` (String(11), nullable — for international wires needing a correspondent bank), `updated_by` (FK `users.id`, `ondelete="SET NULL"`), timestamps.

**Security requirements, not optional:**
- Every read-path (list/get endpoints, CSV export if you add one) must **mask `account_number` and `iban` to only the last 4 characters** (e.g. `"••••••1234"`) in the API response — the full value should never round-trip back to a browser after creation. If a masked value is submitted back on an update, the CRUD layer must detect it's masked and leave the stored value unchanged rather than overwriting real data with literal bullet characters.
- Restrict every `SupplierBankAccount` endpoint (list/create/update/delete, and the CSV upload/delete-all for this dataset) to administrators only — reuse the existing `_require_admin` check pattern from `app/routers/gl_accounts.py` / `app/routers/commodity.py`, don't make banking data readable by a plain authenticated user the way GL accounts or commodity codes are.
- Do not log full account numbers/IBANs anywhere (structured logging, error messages, activity logs) — mask before logging, same rule as before display.

### 4. CRUD (`app/crud/supplier_address.py`, `app/crud/supplier_bank_account.py`, new files)

Standard list-by-supplier / create / update / delete, plus `set_default_address(db, supplier_id, address_type, address_id)` and `set_primary_bank_account(db, supplier_id, account_id)` that un-set the previous default/primary the same way `crud/address.py` does for users. Bulk-upsert + delete-all functions for the CSV import path, matching `bulk_upsert_gl_accounts` / `delete_all_gl_accounts` in `app/crud/gl_account.py` — but scope delete-all to a `supplier_id` filter option too (an admin resetting one bad import shouldn't have to wipe every supplier's banking data).

### 5. Routers

Extend `app/routers/suppliers.py` (or add `app/routers/supplier_master_data.py`, new file, mounted under the existing `/suppliers` prefix — match whichever convention `app/routers/suppliers.py` already uses for sub-resources like hierarchy/duplicates) with:
- `GET/POST/PATCH/DELETE /suppliers/{supplier_id}/addresses`, `POST /suppliers/{supplier_id}/addresses/{id}/set-default`
- `GET/POST/PATCH/DELETE /suppliers/{supplier_id}/bank-accounts` (admin-only per the security note above), `POST /suppliers/{supplier_id}/bank-accounts/{id}/set-primary`
- Master-data bulk endpoints, admin-only, same shape as `/gl-accounts/upload` + `/gl-accounts` (DELETE) + `/gl-accounts/count`:
  - `POST /suppliers/master-data/upload` (CSV of supplier header fields — name, legal_name, tax_id, duns_number, etc. — upsert by `external_supplier_code` if present, else by exact `name` match, and clearly document which)
  - `POST /suppliers/addresses/master-data/upload` (CSV needs a `supplier_external_code` or `supplier_id` column to resolve which supplier each address belongs to — reject rows that don't resolve, same as the GL-mapping-upload's "reject, don't orphan" rule in `bulk_upsert_commodity_account_mappings`)
  - `POST /suppliers/bank-accounts/master-data/upload` (same resolution rule; admin-only)
  - `DELETE` + `/count` variants for all three

### 6. Frontend

Add a "Supplier Master Data" section to `frontend/app/dashboard/settings/page.tsx`, copying the `MasterDataCard` component already built there — three cards (Supplier Header Data, Supplier Addresses, Supplier Bank Accounts). The bank accounts card should visibly note "account numbers are masked after upload" near its upload control so admins aren't surprised the value doesn't echo back in full.

### 7. Migration + tests

One new migration adding all three new tables/columns (check for the current single head first, per the conventions above). Real-DB tests for: only one default address per `(supplier_id, address_type)`, only one primary bank account per supplier, bank account number/IBAN come back masked from the list/get endpoints, a masked value submitted on update does not overwrite the real stored value, and the master-data upload rejects (with a row-level error, not a crash) an address/bank-account row whose supplier reference doesn't resolve.
