# Prompt: Master Data Phase 2 — Currency/FX, Org Structure (Dept/Cost Center/Plant), Payment Terms/Incoterms/UOM

Three independent phases, hand to Copilot one at a time, in this order (no hard dependency between them, but Phase 2 references the same tenant-sentinel pattern used everywhere else, so doing it after Phase 1 here isn't required — just a sane default order by value). After each phase: run its tests plus the existing commodity/GL-account test suite before starting the next.

This follows the same "admin-loadable master data, replacing a free-text field with a real table" pattern already shipped for commodity codes and GL accounts (`app/models/gl_account.py`, `app/crud/gl_account.py`, `app/routers/gl_accounts.py`, `app/services/master_data_import.py`, the "Master Data" section in `frontend/app/dashboard/settings/page.tsx`). Point Copilot at those as the literal reference implementation for every phase below — same shape: admin-only CSV upload with row-level errors (not silent garbage-in), delete-all as a full reset, one Settings card per dataset with a row count, column-alias-tolerant parsing added to `app/services/master_data_import.py` rather than a new module.

---

## Context (same conventions as every other phase in this repo)

FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 backend, Next.js frontend. Dev order: model → schema → CRUD → router → migration → tests → real-DB SQLite smoke test. Tenant-scoped tables use the `NO_TENANT_ID` sentinel from `app.models.document_numbering` (all-`f`, never all-zero). Tests follow the plain `def test_x(): asyncio.run(run_test())` + in-memory SQLite pattern already in every `tests/integration/*.py` file — no `@pytest.mark.asyncio`. Check `alembic/versions/` for the single current head before writing a new migration. All IDs are `UUID(as_uuid=True)`, timestamps `DateTime(timezone=True)`, money `Numeric(12, 2)`.

**Current gap driving all three phases:** `currency` is a free ISO-4217 string column on `Supplier`, `PurchaseOrder`, and `ProcurementInvoice` (`app/models/procurement.py`, `app/models/supplier.py`) with no exchange-rate table anywhere, so nothing can actually convert or roll up spend across currencies today. `Budget.scope_level` (`app/models/accounting_split.py`) accepts `"cost_center"` / `"department"` as free-text `scope_code` strings with zero validation — same unvalidated-free-text problem GL accounts had before today's fix. `incoterms`, `payment_terms`, and `unit_of_measure` are likewise free strings on `PurchaseOrder` / `Supplier` / `PurchaseOrderLineItem` with no lookup table, so nothing stops a typo'd `"Net 3o"` or `"EACH"` vs `"EA"` inconsistency.

---

## Phase 1 — Currency master + exchange rates

**New model `Currency`** (`app/models/currency.py`, new file): `code` (String(3), primary key, ISO 4217, e.g. `"USD"`), `name` (e.g. "US Dollar"), `symbol` (nullable, e.g. "$"), `is_active`, timestamps. Not tenant-scoped — currencies are a global fact, not a per-tenant configurable.

**New model `ExchangeRate`** (`app/models/currency.py`): `id`, `from_currency` (FK `currencies.code`), `to_currency` (FK `currencies.code`), `rate` (Numeric(18, 8) — FX needs more precision than money fields), `as_of_date` (Date, not DateTime — rates are daily), `source` (nullable string, e.g. "manual", "ECB", for audit trail), timestamps. Unique constraint `(from_currency, to_currency, as_of_date)`.

**CRUD** (`app/crud/currency.py`, new file): `get_rate(db, from_currency, to_currency, as_of_date=None) -> ExchangeRate | None` (defaults to the most recent rate on/before the given date, or today if unspecified — same "most-specific/most-recent wins" fallback shape used elsewhere in this codebase, e.g. `resolve_gl_account`), `convert(db, amount, from_currency, to_currency, as_of_date=None) -> Decimal | None` (returns `None` rather than raising if no rate is found — every caller must handle "can't convert" explicitly, don't let this silently return the unconverted amount). Bulk-upsert + delete-all for both `Currency` and `ExchangeRate`, matching the GL-account CSV pattern.

**Router** (`app/routers/currency.py`, new file, mounted at `/api/v1/currencies` and `/api/v1/exchange-rates`): standard list/upload/delete-all/count for both datasets, admin-only writes, any-authenticated-user reads (same gating as commodity codes, not the stricter admin-only-read gating used for supplier banking data).

**Use it somewhere real, don't just build an inert table:** add a "converted to tenant reporting currency" figure to the existing spend analytics endpoint (`app/routers/analytics.py` / wherever `getSpendAnalytics` is served from) using `convert()` — pick the tenant's default currency as whatever `Supplier`/PO documents predominantly use today if there's no explicit tenant-currency setting, and note in the response when a document's currency couldn't be converted (missing rate) rather than silently dropping it from the total.

**Frontend:** two Master Data cards (Currencies, Exchange Rates) in Settings, same `MasterDataCard` component already there.

**Tests:** rate resolution picks the most recent rate on/before a given date, not a future one; `convert()` returns `None` (not an exception, not a silent 1:1 passthrough) when no rate exists; delete-all resets each of the two datasets independently.

---

## Phase 2 — Organizational master data: Departments, Cost Centers, Plants

Replaces the unvalidated free-text `scope_code` problem on `Budget` (`app/models/accounting_split.py`, `BUDGET_SCOPE_LEVELS = ("gl_account", "cost_center", "department")`) the same way Phase 0 fixed it for GL accounts, plus adds a `Plant` concept for ship-to/tax-jurisdiction purposes (referenced as a gap in the enterprise procurement work but never built).

**New model `Department`** (`app/models/org_structure.py`, new file): `id`, `tenant_id` (NO_TENANT_ID pattern), `code`, `name`, `parent_department_id` (self-referential FK, nullable, for a department hierarchy), `is_active`, timestamps. Unique `(tenant_id, code)`.

**New model `CostCenter`** (same file): `id`, `tenant_id`, `code`, `name`, `department_id` (FK `departments.id`, nullable), `is_active`, timestamps. Unique `(tenant_id, code)`.

**New model `Plant`** (same file): `id`, `tenant_id`, `code`, `name`, `address_line1`, `address_line2`, `city`, `state_province`, `postal_code`, `country`, `tax_id` (plant-level tax registration, distinct from a supplier's), `is_active`, timestamps. Unique `(tenant_id, code)`.

**Tighten `Budget`**: add nullable `cost_center_id` FK (alongside the existing free-text `scope_code`, don't remove it — same denormalized-plus-FK approach used for `CommodityAccountMapping.gl_account_id`) so a `cost_center`-scoped budget can optionally resolve to a real `CostCenter` row; resolve it in `crud/budget.py` the same way `bulk_upsert_commodity_account_mappings` resolves `gl_account_code` against `gl_accounts` — reject/report, don't silently orphan.

**CRUD + router + frontend:** same shape as Phase 1 — list/upload/delete-all/count per dataset (three datasets: Departments, Cost Centers, Plants), admin-only writes, Master Data Settings cards.

**Tests:** cost-center CSV upload correctly links to an existing department when `department_code` is given and rejects (with a row-level error) an unresolvable `department_code`; a `Budget` upload/creation referencing a nonexistent cost center is rejected the same way an unresolvable GL account is today.

---

## Phase 3 — Payment Terms, Incoterms, Units of Measure (three small lookup tables)

Smallest phase — three flat lookup tables, no hierarchy, quick win for data consistency.

**New model `PaymentTerm`** (`app/models/lookup_tables.py`, new file): `id`, `tenant_id`, `code` (e.g. `"NET30"`), `description` (e.g. "Net 30 days"), `net_days` (Integer, nullable), `discount_percent` (Numeric(5,2), nullable), `discount_days` (Integer, nullable — supports "2/10 Net 30" style terms), `is_active`, timestamps. Unique `(tenant_id, code)`.

**New model `Incoterm`** (same file): `id`, `code` (e.g. `"FOB"`, `"DDP"` — the actual 11 Incoterms 2020 codes, not tenant-configurable, this is a fixed international standard), `description`, `is_active`. Seed all 11 current Incoterms 2020 codes directly in the migration (this is a small, stable, standardized list — unlike UNSPSC, it's fine to hand-seed in full).

**New model `UnitOfMeasure`** (same file): `id`, `code` (e.g. `"EA"`, `"BX"`, `"KG"`), `description`, `uom_type` (nullable, e.g. `"count"`, `"weight"`, `"volume"` — for sanity-checking conversions), `is_active`. Seed a reasonable common set (EA, CS, BX, PK, KG, LB, L, GAL, HR, DAY) in the migration; leave uncommon ones to CSV import.

**New model `UOMConversion`** (same file): `id`, `from_uom` (FK), `to_uom` (FK), `factor` (Numeric(18, 8) — multiply a quantity in `from_uom` by this to get `to_uom`), unique `(from_uom, to_uom)`.

**CRUD + router + frontend:** same shape as prior phases — four datasets (Payment Terms, Incoterms, UOM, UOM Conversions), Incoterms/UOM base list are global reads for any user, Payment Terms are tenant-scoped, admin-only writes throughout.

**Tests:** the 11 seeded Incoterms exist after migration; a UOM conversion resolves correctly in both directions if you choose to auto-generate the inverse factor (`1/factor`) — decide and document whether inverse rows must be uploaded explicitly or are derived, don't leave it ambiguous; delete-all resets each of the four datasets independently.

---

## Explicitly out of scope for this phase (larger asks from the same taxonomy, revisit only if actually needed)

- **Company Codes / Purchasing Organizations** (SAP-style multi-legal-entity structure) — S2PNexus today is architected as a single unified platform, not a dual upstream/downstream system needing entity-level books separation. Only worth building if there's a real near-term need for multiple legal entities with separate financials.
- **WBS Elements / Internal Orders / Asset Numbers** — deep SAP-specific concepts; skip unless there's an actual SAP integration target.
- **Catalog data (internal + PunchOut/cXML)** — a real gap, but a large one (catalog items, pricing tiers, supplier part number mapping, PunchOut protocol) deserving its own dedicated prompt rather than folding in here — ask for it separately if/when ready to scope it.
- **Tax master data / jurisdiction-based tax calculation** — `tax_code` stays free text for now; a real tax engine (jurisdiction rules, rate tables) is its own significant phase, not a quick lookup table like Incoterms/UOM.
- **RFI/RFP/RFQ scoring & weighting templates** — `SourcingEventResponse.evaluation_score` already exists as a plain number; a configurable weighted-criteria rubric is a real feature but sourcing-specific, not master data in the same sense as the rest of this document — worth its own prompt against `app/models/sourcing.py` if wanted.
- **EDI/cXML supplier routing parameters** — only relevant if/when there's an actual EDI or PunchOut integration to route to; the `SupplierAddress`/`SupplierBankAccount` work already in progress covers the master-data side (remit-to, banking) that real P2P transactions need regardless of integration protocol.

Already covered, no new prompt needed: **Commodity Codes** (Phase 0 + the GL Accounts work today), **Contract Types & Clause Library** (`ContractTemplate`/`ContractClause` already exist), **Users/Groups/Roles/Approvals** (`UserRole` + the Workflow Automation engine's N-of-M approvals already exist).
