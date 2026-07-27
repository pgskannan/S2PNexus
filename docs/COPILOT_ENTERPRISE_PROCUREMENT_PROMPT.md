# Prompt: Enterprise-grade Purchase Order / Goods Receipt / Invoice / Invoice Verification

Copy each phase below into Copilot (or whichever AI coding tool) **one at a time, in order**. Dependency chain: Phase 2 needs Phase 0 (commodity/GL) and Phase 1 (addresses); Phase 3 needs Phase 2; Phase 4 needs Phase 2 and Phase 3; Phase 5 needs Phase 0, Phase 2, and Phase 4. Do not skip ahead. After each phase, run its tests and the existing procurement/supplier suites before starting the next one.

Paste the "Context for every phase" block once at the start of the session (or repeat it if the tool's context resets between phases), then paste one phase's prompt.

---

## Context for every phase (paste once)

You are working in the S2PNexus backend, a FastAPI + SQLAlchemy 2.0 async + Alembic + Pydantic v2 codebase. Follow these existing conventions exactly — they are not optional style preferences, they are how every other domain in this codebase is built and tested:

1. **Dev order**: model → Pydantic schema → CRUD function → router endpoint → Alembic migration → tests → a real (non-mocked-at-the-DB-layer) smoke test against SQLite. Do not skip the real-DB test step — this codebase has already caught at least one serious bug (a sentinel value silently corrupted by SQLite's NUMERIC column affinity) that only a real-DB test would catch.
2. **Route registration order**: in any router, literal-prefixed routes (e.g. `/purchase-orders/matching-exceptions`) must be registered *before* `/{param}`-shaped routes of the same shape (e.g. `/purchase-orders/{id}`), or the literal route gets shadowed and 404s/422s. Add a regression test for this for every new literal route you add alongside an existing `{id}` route.
3. **Reuse the generic Workflow Automation engine** (`app/models/workflow.py`, `app/crud/workflow.py`) for any new approval/exception-routing step instead of inventing a new approval mechanism. It already supports condition/approval/notification step types, N-of-M approvals, and escalation, keyed by an `entity_type` string + `entity_id` UUID — attach new entity types to it (`"purchase_order"`, `"goods_receipt"`, `"invoice_match_exception"`, `"budget_override"`) rather than building bespoke approval tables.
4. **Reuse document numbering** (`app/crud/document_numbering.py`, `generate_document_number()`) for any new document-like entity that needs a human-readable number — do not hand-roll numbering again.
5. **Tenant scoping**: pass `tenant_id=current_user.tenant_id` through router → CRUD call sites, same as the existing `create_purchase_order` / `create_goods_receipt` / `create_invoice` functions in `app/crud/procurement.py` already do. Any new tenant-configurable table (address books, commodity mappings, budgets) should reuse the exact tenant-resolution pattern from `app.models.document_numbering`: a fixed sentinel UUID for "no tenant" (`NO_TENANT_ID`, all-`f`, **never all-zero** — see that module's docstring for the SQLite bug an all-zero sentinel causes), with tenant-specific rows falling back to a global-default row.
6. **Testing pattern**: this sandbox's pytest (8.2.0) + pytest-asyncio (0.23.3) combination breaks on async generator fixtures. Every existing test file in `tests/integration/` uses a plain `def test_x(): asyncio.run(run_test())` wrapper with a self-contained in-memory SQLite session helper instead of `@pytest.mark.asyncio` — follow that exact pattern, don't introduce `pytest-asyncio` fixture usage.
7. **Migrations**: check `alembic/versions/` for the current single head before writing a new migration's `down_revision` — this repo has been bitten before by two people/sessions branching off the same head and creating a revision-ID collision. Confirm there's exactly one head after you add yours.
8. All monetary fields are `Numeric(12, 2)`; all IDs are `UUID(as_uuid=True)` from `sqlalchemy.dialects.postgresql`; timestamps are `DateTime(timezone=True)`.
9. **Validated state-machine mutations**: whenever you add a lifecycle/status transition, validate the transition is legal for the current state *before* mutating anything — mirror `transition_supplier_lifecycle()` in `crud/supplier.py`, which has a comment explaining a real past bug from mutating before validating.

Current state you're upgrading from (all in `app/models/procurement.py`, `app/schemas/procurement.py`, `app/crud/procurement.py`, `app/routers/procurement.py`):
- `PurchaseOrder` has no line items at all — just a header with `total_amount`. No addresses, no incoterms, no payment terms, no supplier acknowledgment, no shipping cost allocation.
- `GoodsReceipt` has no line items either — just header-level `received_quantity` / `returned_quantity` integers for the *entire* PO, so partial/multi-shipment receiving against individual PO lines is not actually possible today.
- `ProcurementInvoice` has no line items. `match_invoice()` in `crud/procurement.py` does **not compare any actual amounts, quantities, or receipts** — it only flips `match_status` to `"matched"` if `match_type` is a recognized string. There is no real 2-way or 3-way matching logic today.
- Duplicate invoice detection (`invoice.duplicate_status`) is a placeholder heuristic (`invoice_number.lower().endswith("dup")`), not real detection.
- `commodity` and `category` on `ProcurementRequisitionLineItem` (and the requisition header) are free-text strings today — no standard taxonomy, no link to a GL account, no way to configure match rules or receiving behavior per commodity.
- There is no address book anywhere — no concept of a user's default ship-to location, no shared company addresses, nothing on `PurchaseOrder` to hold a ship-to/bill-to address at all yet (that's added in Phase 2, sourced from Phase 1).
- There is no accounting split/distribution concept — a line item can only ever be coded to one GL account, in full. There is no budget concept at all — nothing checks or tracks committed/actual spend against a budget anywhere in the codebase today.

---

## Phase 0 — Commodity code master data (UNSPSC), GL account mapping, matching/receiving policy

This phase has no dependencies and everything else builds on it. It's the foundation for: a real commodity taxonomy (UNSPSC) instead of free text, GL account codes that auto-populate from the commodity code instead of manual entry, and configurable-per-commodity-code matching (2-way vs 3-way) and auto-receipt behavior.

**New model `CommodityCode`** (`app/models/commodity.py`, new file): represents one node of the UNSPSC hierarchy. `id`, `code` (the full UNSPSC code, e.g. `"43211500"` — segment+family+class+commodity, 8 digits), `segment_code` (first 2 digits), `segment_title`, `family_code` (first 4 digits), `family_title`, `class_code` (first 6 digits), `class_title`, `commodity_title` (the leaf-level, most specific name), `is_active` (bool, default True). Index `code` uniquely.

Do **not** hand-seed the full UNSPSC taxonomy (the official list is ~50,000+ codes) via an Alembic migration — that's the wrong tool for a dataset that size and changes on UNSPSC's own release cycle. Instead build a one-time import path: either a `scripts/import_unspsc.py` CLI script that reads the official UNSPSC CSV/Excel export (from the GS1/UNSPSC organization) and bulk-inserts it, or an admin-only `POST /commodity-codes/import` endpoint that accepts an uploaded CSV in the same shape. Seed only a small handful of realistic example codes in the migration itself (enough for tests and a working demo), and note in the migration's docstring that the full taxonomy is expected to be imported separately.

**New model `CommodityAccountMapping`** (tenant-configurable, reuse the tenant-sentinel pattern from the Context block, don't invent a new one): `id`, `tenant_id`, `scope_level` (`"segment"` | `"family"` | `"class"` | `"commodity"` — which level of the UNSPSC hierarchy this mapping applies to), `scope_code` (the segment/family/class/commodity code string this mapping matches), `gl_account_code`, `gl_account_description`, `cost_center` nullable, `updated_by` FK users nullable, timestamps. Unique constraint on `(tenant_id, scope_level, scope_code)`.

**New model `CommodityMatchingPolicy`** (same tenant + scope pattern as `CommodityAccountMapping` — share the scope-resolution helper function between both rather than duplicating it): `id`, `tenant_id`, `scope_level`, `scope_code`, `required_match_type` (`"two_way"` | `"three_way"`, default `"two_way"`), `auto_receive` (bool, default False — when true, POs for this commodity get an automatically-generated goods receipt instead of requiring manual receiving; see Phase 3), `updated_by`, timestamps. Unique constraint on `(tenant_id, scope_level, scope_code)`.

**CRUD** (`app/crud/commodity.py`, new file):
- `resolve_gl_account(db, tenant_id, commodity_code) -> CommodityAccountMapping | None` and `resolve_matching_policy(db, tenant_id, commodity_code) -> CommodityMatchingPolicy | None`: both walk from most-specific to least-specific scope (commodity-level exact match first, then its class, then family, then segment, then the tenant's own configured default, then the global default, then `None` if nothing configured anywhere — same multi-tier fallback shape as `get_numbering_format` in `app.crud.document_numbering`, reuse that shape).
- `upsert_commodity_account_mapping(...)` / `upsert_commodity_matching_policy(...)`: admin config CRUD, same shape as `upsert_numbering_format`.
- `search_commodity_codes(db, query, limit)`: for a line-item form's commodity-code picker/autocomplete.

**Router** (`app/routers/commodity.py`, new file, mounted at `/api/v1/commodity-codes`): `GET /commodity-codes?search=` (autocomplete), `GET /commodity-codes/{code}/resolved` (returns the resolved GL account + matching policy + auto_receive for this tenant in one call — this is what a line-item entry form calls the moment a user picks a commodity code, so the GL account field can auto-populate immediately), admin-only `GET/PUT` for the account-mapping and matching-policy config lists (mirror `app/routers/document_numbering.py`'s list/upsert/admin-check shape exactly).

**Migration + tests**: new tables, a small seed set of example UNSPSC codes + at least one mapping + one policy at each scope level (segment/family/class/commodity) so the most-specific-wins fallback logic can actually be tested, plus real-DB tests for: exact commodity-level match wins over its own class/family/segment defaults, falling back correctly when only a family-level mapping exists, and falling back to the tenant's own default over the global default.

---

## Phase 1 — Address book: ship-to/bill-to resolution from user profile, with custom override

No dependency on Phase 0. Both `create_requisition` and Phase 2's `create_purchase_order` consume this.

**New model `Address`** (`app/models/address.py`, new file): `id`, `tenant_id`, `label` (e.g. `"HQ - Building 3"`, `"East Warehouse"`), `owner_type` (`"user"` | `"tenant"` — a user's personal saved address vs. a company-wide shared one any requester can pick, like a central receiving dock), `owner_id` (nullable when `owner_type="tenant"`), `attention_to`, `address_line1`, `address_line2`, `city`, `state_province`, `postal_code`, `country`, `phone`, `is_default` (bool — a user's own default address; only one per user should be True, enforce in CRUD not just a DB constraint since "only one true per owner" isn't expressible as a simple unique index).

**CRUD** (`app/crud/address.py`, new file): `list_addresses_for_user(db, user_id, tenant_id)` (returns the user's own addresses plus all `owner_type="tenant"` shared addresses for their tenant), `get_default_address_for_user(db, user_id) -> Address | None`, standard create/update/delete/set-default for a user's own addresses, admin-only create/update/delete for tenant-shared addresses.

**Snapshot, don't just reference**: any entity that uses an address (Phase 2's `PurchaseOrder`, and `ProcurementRequisition` if you want ship-to at the requisition stage too) should store both an optional `*_address_id` FK **and** denormalized text fields (`ship_to_name`, `ship_to_address_line1`, `ship_to_city`, etc. — copy every field at the moment of use). This is important: if a saved `Address` is later edited or deleted, historical POs must keep showing what was actually shipped-to at the time, not silently change. The FK is for "was this sourced from a saved address" traceability and re-use in a picker UI; the text fields are the source of truth for display and for Phase 2's PDF/print output. For a fully custom one-off address (the "custom address" requirement), leave `*_address_id` null and just fill the text fields directly — don't force every shipment through the saved address book.

**Default-then-override flow**: when a requisition or PO is created, pre-fill ship-to from `get_default_address_for_user(requester)` (snapshotting immediately per the rule above); the requester/buyer can then either pick a different saved address (their own or a tenant-shared one) or type a fully custom one-off address instead, before submitting.

**Router**: `GET /addresses/mine`, `POST /addresses/mine`, `PATCH /addresses/mine/{id}`, `DELETE /addresses/mine/{id}`, `POST /addresses/mine/{id}/set-default`, `GET /addresses/shared` (tenant-wide, any authenticated user can read, admin-only to write), `GET /addresses/default` (convenience lookup a requisition/PO creation form calls to pre-fill).

**Migration + tests**: new table, plus real-DB tests for: only one address can be default per user (setting a new default un-defaults the old one, don't just allow two), a shared tenant address is visible to any user in that tenant, and editing a saved `Address` does not retroactively change a field that was already snapshotted onto an existing requisition/PO.

---

## Phase 2 — Purchase Order: line items, commercial terms, shipping, addresses, real lifecycle

Requires Phase 0 (`CommodityCode` / `resolve_gl_account`) and Phase 1 (`Address` / snapshot pattern). Upgrade `PurchaseOrder` to a proper enterprise PO:

**New model `PurchaseOrderLineItem`** (`app/models/procurement.py`): `id`, `purchase_order_id` FK, `line_number` (int, order within the PO), `requisition_line_item_id` FK to `procurement_requisition_line_items` nullable (traceability back to the source requisition line, if any), `description`, `commodity_code_id` FK to `commodity_codes` nullable (replaces the old free-text `commodity`/`category` fields — keep a `commodity_code_free_text` fallback column for the rare case nothing in the taxonomy fits, but the picker should push people toward a real code), `quantity` (Numeric), `unit_of_measure` (string, e.g. "EA", "CASE", "HR"), `unit_price`, `line_total`, `tax_code` (string, e.g. "STANDARD", "EXEMPT", "REDUCED" — just a string field, not a full tax master table), `tax_amount`, `account_code` (GL account — see below), `account_code_is_override` (bool, default False), `allocated_shipping_amount` (Numeric, default 0 — this line's share of the PO's total shipping cost, see below), `need_by_date`, `promised_date` nullable (supplier-committed date, filled in on acknowledgment), `notes`.

**GL account auto-population**: whenever `commodity_code_id` is set (or changed) on a line item and `account_code_is_override` is False, call Phase 0's `resolve_gl_account(db, tenant_id, commodity_code)` and set `account_code` from the result. If the caller explicitly supplies an `account_code` at creation/update time, set `account_code_is_override=True` and never auto-overwrite it again on subsequent edits.

**Extend `PurchaseOrder`**: `subtotal`, `tax_total`, `shipping_amount`, `grand_total` (all Numeric, computed from line items on save), `incoterms` (string, e.g. "FOB", "DDP", "EXW"), `payment_terms` (string, e.g. "Net 30"), `buyer_contact_id` FK to users, `supplier_contact_email`, `acknowledgment_status` (`"pending"` | `"acknowledged"` | `"disputed"`, default `"pending"`), `acknowledged_at`, `acknowledged_notes`, plus (from Phase 1) `ship_to_address_id`/`bill_to_address_id` nullable FKs and the full set of snapshotted `ship_to_*`/`bill_to_*` text fields. Extend `lifecycle_status` (new column, mirroring the pattern already used on `ProcurementRequisition`/`Supplier`) through: `draft` → `pending_approval` → `approved` → `sent_to_supplier` → `acknowledged` → `partially_received` → `fully_received` → `closed`, plus `cancelled` reachable from any pre-`fully_received` state. Route the `pending_approval` → `approved` step through the Workflow Automation engine (`entity_type="purchase_order"`) instead of a bespoke approval flag — this is also where Phase 5's budget check plugs in.

**Shipping cost allocation**: add `shipping_allocation_method` (`"prorate_by_value"` | `"prorate_by_weight"` | `"manual"` | `"single_line"`, default `"prorate_by_value"`) on `PurchaseOrder`. `prorate_by_value` splits `shipping_amount` across line items proportional to each line's `line_total` share of the PO subtotal (the common default when weight isn't tracked); `prorate_by_weight` requires a `weight` field on the line item (add it, nullable, only used by this method); `manual` lets the buyer type `allocated_shipping_amount` per line directly; `single_line` puts 100% of the shipping cost on one designated line (e.g. a dedicated "Freight" line). Add a tenant-configurable default freight GL account (a `CommodityAccountMapping`-style row keyed by a reserved `scope_level="commodity", scope_code="FREIGHT"` pseudo-code is the simplest way to reuse Phase 0's existing resolution machinery rather than building a second config table just for this) so allocated shipping amounts have somewhere sensible to be coded by default, still overridable per line via Phase 5's split accounting.

**CRUD**: `create_purchase_order` must now accept a list of line items (each resolving its own GL account per the rule above) plus a `shipping_amount` + `shipping_allocation_method`, compute `subtotal`/`tax_total`/`shipping_amount` allocation/`grand_total` from them (validate they sum correctly, don't trust a client-supplied grand_total), and default ship-to/bill-to from Phase 1's `get_default_address_for_user` if the caller didn't supply an override. Add `transition_purchase_order_lifecycle()` (validate-before-mutate, per the Context block's rule 9). Add `acknowledge_purchase_order()` (supplier-side action, sets `acknowledgment_status`/`acknowledged_at`, optionally updates `promised_date` per line). When the PO transitions to `approved`, for every line item whose Phase 0 `resolve_matching_policy(commodity_code)` has `auto_receive=True`, immediately call Phase 3's receipt-creation logic to auto-generate a full receipt for that line — most POs will have a mix of physical-goods lines (manual receiving) and service/license lines (auto-received) on the same order.

**Router**: `POST /purchase-orders/{id}/lifecycle/transition`, `POST /purchase-orders/{id}/acknowledge`, `GET/POST /purchase-orders/{id}/line-items`. Remember the route-ordering rule from the Context block for any new literal routes under `/purchase-orders/`.

**Migration + tests**: new tables/columns, plus real-DB tests for: line-item total computation, each shipping-allocation method producing correctly-summed per-line amounts (the four methods should all sum back to exactly `shipping_amount`, watch for rounding — allocate remainder cents to the last line rather than losing/gaining a cent), ship-to defaulting from the requester's profile address when none is supplied, a custom one-off address correctly overriding the default, the lifecycle state machine (including an "invalid transition raises" test and a "reject transition without required data" test, mirroring the two equivalent tests in `tests/integration/test_supplier_lifecycle.py`), and a route-order regression test for the new literal routes.

---

## Phase 3 — Goods Receipt: line-item level, partial receiving, quality/inspection, auto-receipt

Requires Phase 2's `PurchaseOrderLineItem` to exist.

**New model `GoodsReceiptLineItem`** (`app/models/procurement.py`): `id`, `goods_receipt_id` FK, `purchase_order_line_item_id` FK, `quantity_received`, `quantity_rejected` (default 0), `quantity_accepted` (computed = received − rejected), `rejection_reason` nullable, `lot_number` nullable, `condition_status` (`"good"` | `"damaged"` | `"wrong_item"` | `"other"`, default `"good"`), `notes`.

**Extend `GoodsReceipt`**: remove/deprecate the flat `received_quantity`/`returned_quantity` header fields in favor of line items (keep the columns but stop writing to them from new code — mark deprecated in a comment; don't drop them in this phase to avoid a breaking migration on top of Phase 2's). Add `received_by` FK to users, `inspected_by` FK to users nullable, `inspection_status` (`"pending"` | `"passed"` | `"failed"` | `"not_required"`), `carrier`, `tracking_number`, `delivery_note_reference`.

**CRUD**: `create_goods_receipt` now takes a list of `{purchase_order_line_item_id, quantity_received, quantity_rejected, condition_status, ...}` entries. For each, validate `quantity_received` doesn't exceed `(PO line ordered quantity − sum of quantity_accepted from all prior receipts against that line)` — if it does, this is an **over-receipt exception**: don't hard-reject it (over-receipt happens in the real world), but set a `has_exceptions` flag on the `GoodsReceipt` and record the variance, then route it through the Workflow Automation engine (`entity_type="goods_receipt"`) for a buyer/AP review task rather than silently accepting it. Add `get_po_line_receipt_status(po_line_item_id)` returning ordered/received/accepted/outstanding quantities — this is what Phase 4's 3-way match will call. After each receipt, recompute the parent `PurchaseOrder.lifecycle_status`: `partially_received` if any line still has outstanding quantity, `fully_received` if all lines are fully received.

**Auto-receipt** (`auto_receive_purchase_order_line(db, po_line_item_id, actor_id)`): called by Phase 2 when a PO line's resolved commodity matching policy has `auto_receive=True`. Creates a `GoodsReceipt` + `GoodsReceiptLineItem` for the full ordered quantity immediately, tagged with a `receipt_type` value of `"auto"` (add this to the existing `receipt_type` field's allowed values alongside whatever's there today) and `received_by` set to a system/service marker rather than a real user, so it's clearly distinguishable from a real physical receipt in any audit trail or the Phase 6 dashboard. This is what makes 3-way matching work for services/software-license lines that will never have a real physical receiving event — without an auto-receipt, those lines would be permanently stuck failing the 3-way match's "don't pay for what wasn't received" check.

**Router**: `POST /purchase-orders/{id}/receipts` (extend existing endpoint to accept line items), `GET /purchase-orders/{id}/receipt-status` (rollup across all receipts for that PO).

**Migration + tests**: new table + columns, plus real-DB tests for: a single full receipt marking the PO `fully_received`, two partial receipts against the same PO line correctly summing to the outstanding quantity and only marking `fully_received` after the second, an over-receipt correctly setting `has_exceptions` + creating a workflow task instead of silently succeeding or hard-failing, and a PO line with an `auto_receive` commodity policy getting an automatic `"auto"`-typed receipt the moment the PO is approved, with no manual receiving action involved.

---

## Phase 4 — Invoice + real 3-way match / Invoice Verification engine

Requires Phase 2 and Phase 3's line-item tables to exist. This is the phase that actually delivers "invoice verification" — today it's a status flag with no real comparison logic, per the Context block above.

**New model `ProcurementInvoiceLineItem`** (`app/models/procurement.py`): `id`, `invoice_id` FK, `purchase_order_line_item_id` FK nullable (nullable because non-PO / memo invoices can exist), `description`, `quantity`, `unit_price`, `line_total`, `tax_amount`.

**New model `InvoiceMatchException`**: `id`, `invoice_id` FK, `invoice_line_item_id` FK nullable, `exception_type` (`"price_variance"` | `"quantity_variance"` | `"quantity_exceeds_receipt"` | `"missing_receipt"` | `"duplicate_invoice"` | `"tax_variance"`), `expected_value`, `actual_value`, `variance_amount`, `variance_percent`, `resolution_status` (`"open"` | `"approved_with_variance"` | `"rejected"` | `"resolved"`), `resolved_by` FK users nullable, `resolved_at` nullable, `resolution_notes` nullable, `created_at`.

**Match type is resolved automatically per line, not passed in manually.** Each invoice line item carries (via its linked PO line item's `commodity_code_id`) a `resolve_matching_policy()` lookup that says whether *that specific line* requires two-way or three-way matching. A single invoice can therefore have some lines needing only a PO-price/quantity check and others needing the full three-way check against receipts, in the same match run. `match_type` as a caller-supplied parameter becomes an optional **override**, not the primary mechanism.

**Real matching engine** — replace `match_invoice()` in `crud/procurement.py` entirely:
- `perform_invoice_match(db, invoice_id, match_type_override=None)`:
  - For each invoice line item, determine its effective match type: `match_type_override` if supplied, else Phase 0's `resolve_matching_policy(tenant_id, commodity_code)` via the line's linked PO line item, else a tenant-level fallback default of `"two_way"`.
  - **Two-way lines (invoice vs PO)**: compare `unit_price` and `quantity` against the linked PO line. Variance within `matching_tolerance_amount` / `matching_tolerance_percent` → no exception. Variance beyond tolerance → create an `InvoiceMatchException` (`price_variance` or `quantity_variance`), don't silently reject.
  - **Three-way lines (invoice vs PO vs receipt)**: everything two-way does, plus call Phase 3's `get_po_line_receipt_status()` and flag `quantity_exceeds_receipt` if the invoiced quantity exceeds what's actually been accepted for that line.
  - **Duplicate detection**: replace the `.endswith("dup")` placeholder with real logic — flag `duplicate_invoice` if another invoice exists for the same `supplier_id` with either the same `invoice_number`, or the same `amount` within a configurable date-proximity window (reuse the multi-factor scoring approach from `crud/supplier.py`'s `find_potential_duplicate_suppliers`).
  - Sets `invoice.match_status` to `"matched"`, `"matched_with_variance"`, or `"exception"`.
  - When exceptions exist, create a Workflow Automation task (`entity_type="invoice_match_exception"`) routed to an AP clerk role.
- `resolve_invoice_match_exception(db, exception_id, resolution_status, resolution_notes, resolved_by)`: AP clerk action to close out an exception; re-runs status computation when all of an invoice's exceptions are resolved.

**Router**: `POST /invoices/{id}/match` (body becomes `{match_type_override?: string, tolerances?}`, all optional), `GET /invoices/{id}/exceptions`, `POST /invoices/exceptions/{exception_id}/resolve`, `GET /invoices/matching-exceptions` (AP clerk worklist — **register this literal route before** the existing `/invoices/{invoice_id}` shaped routes).

**Migration + tests**: new tables, plus real-DB tests covering: a clean 3-way match with no exceptions, a price-variance-within-tolerance match, a price-variance-beyond-tolerance match (exception + workflow task), a quantity-exceeds-receipt exception, a duplicate-invoice detection case, exception resolution flipping the invoice's overall `match_status`, an invoice whose lines resolve to *different* match types matching correctly per line, and a `match_type_override` correctly forcing three-way on a line whose commodity policy would otherwise resolve to two-way.

---

## Phase 5 — Split accounting & budget control

Requires Phase 0 (GL accounts), Phase 2 (PO line items), and Phase 4 (invoice line items / match status — budget "actual" is driven off matched invoices).

**New model `LineItemAccountingSplit`** (`app/models/accounting_split.py`, new file): polymorphic, mirroring the `entity_type`/`entity_id` convention already used by the Workflow engine rather than three near-identical split tables. `id`, `line_item_type` (`"requisition_line"` | `"po_line"` | `"invoice_line"`), `line_item_id`, `split_method` (`"percentage"` | `"amount"`), `percentage` nullable, `amount` nullable, `gl_account_code`, `cost_center` nullable, `department` nullable, `project_code` nullable, `created_at`.

**Validation**: for any given `(line_item_type, line_item_id)`, all its `percentage` splits must sum to exactly 100, or all its `amount` splits must sum to exactly the line's `line_total` — validate this in CRUD before committing, don't trust the client. **Default behavior**: when a line item is created with only its single auto-resolved GL account and no explicit splits are supplied, auto-create one 100%/full-amount split row pointing at that account — every line item should always have at least one split row, so budget/reporting logic never needs an "un-split" special case.

**Splits carry through the document chain**: when a PO line is generated from a requisition line, copy the requisition line's splits as the PO line's starting splits (still editable before PO approval, same validation rule applies to any edit). When an invoice line is matched to a PO line, default to the PO line's splits unless corrected on the invoice.

**CRUD** (`app/crud/accounting_split.py`, new file): `set_line_item_splits(db, line_item_type, line_item_id, splits)` (replace-all, validated), `get_line_item_splits(db, line_item_type, line_item_id)`, `copy_splits(db, from_type, from_id, to_type, to_id)` (used by the requisition→PO and PO→invoice carry-through above).

**New model `Budget`** (tenant-scoped): `id`, `tenant_id`, `fiscal_year`, `fiscal_period` nullable (null = whole-year budget), `scope_level` (`"gl_account"` | `"cost_center"` | `"department"`), `scope_code`, `budgeted_amount`, `enforcement` (`"hard"` | `"soft"` | `"none"`, default `"soft"` — hard blocks the approval transition outright, soft allows an approver to proceed with a required override reason logged via the Workflow Automation engine's `entity_type="budget_override"`, none is tracking-only).

**Don't build a separately-maintained running-balance ledger table for this first pass** — compute `committed` and `actual` live via aggregation queries instead, to avoid the class of bug where a maintained running total drifts out of sync with reality:
- `committed` = sum of `LineItemAccountingSplit` amounts (resolved to a dollar amount even for percentage splits, using the line's `line_total`) for PO lines whose parent PO is in `approved` through `partially_received`/`fully_received` lifecycle states and not yet fully invoiced, matching the budget's `scope_level`/`scope_code`/fiscal period.
- `actual` = the same aggregation over invoice line splits, restricted to invoices with `match_status` in `("matched", "matched_with_variance")`.
- `available = budgeted_amount - committed - actual`.

If these aggregation queries become a performance problem at scale later, that's a future optimization (a maintained ledger updated via triggers or on-write) — don't build that now, it's premature for this phase.

**Budget check** `check_budget_availability(db, tenant_id, gl_account_code, cost_center, fiscal_year, fiscal_period, requested_amount) -> BudgetCheckResult`: called from Phase 2's requisition/PO approval transition. If `enforcement="hard"` and `requested_amount > available`, raise the same kind of `ValueError` the existing lifecycle transition functions already raise on an invalid transition (don't invent a different error-handling convention). If `"soft"`, allow the transition but attach the over-budget warning to the Workflow Automation approval task so the approver sees it and must supply an override reason to proceed.

**Router**: admin CRUD for `Budget` rows (`/budgets`), `GET /budgets/check` (preview endpoint an approval screen calls before submitting, so the requester sees "this will put GL account X at 110% of budget" before hitting submit, not just as a rejection after the fact).

**Migration + tests**: new tables, plus real-DB tests covering: a split set with percentages summing to 100 accepted, one summing to 99 rejected, splits correctly carrying from requisition line → PO line → invoice line (and a manual correction on the invoice line not disturbing the PO line's own splits), a hard-budget check correctly blocking PO approval when over budget, a soft-budget check allowing approval with a flagged override requirement, and `committed` correctly reflecting an approved-but-not-yet-invoiced PO while `actual` only reflects matched invoices (i.e. committed should drop / actual should rise as a PO's lines get invoiced and matched — a full lifecycle test, not just a snapshot).

---

## Phase 6 (optional stretch) — AP worklist & reporting

Only do this after Phases 0–5 are done, tested, and reviewed. A read-only dashboard: open matching exceptions by age/type/supplier, PO cycle time (created → fully_received), on-time-receipt rate against `need_by_date`/`promised_date`, spend-by-commodity-code and spend-by-GL-account breakdowns, and budget utilization (budgeted vs. committed vs. actual vs. remaining, by GL account/cost center/department/fiscal period). Follow the same read-only-dashboard pattern already used for the Agent Activity dashboard (`app/models/agent_activity.py`, `app/routers/ai.py`'s `/agents/activity` endpoints, `frontend/app/dashboard/agent-activity/page.tsx`) rather than inventing a new dashboard pattern.
