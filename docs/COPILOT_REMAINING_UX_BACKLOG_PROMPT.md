# Copilot Prompt — Remaining P2P UX Backlog (2026-08-04)

Written after a Claude session fixed 6 reported UX bugs (receipt detail page, invoice
PO auto-bind, PO cancel cascade, PO history audit trail, approver mouseover, admin
approval-node removal — commit `b3659aa`) and built PO auto-creation's validation gate +
auto-send-to-supplier + auto-close (commit `8f2a371`). Both are pushed to `main`, not yet
deployed. This prompt covers what's still open from the same backlog dump. Each section
below is independent — pick them up in any order, or split across sessions.

**Do not re-touch anything from the two commits above** unless you find an actual bug in
them; they're done and tested (backend: `pytest tests/unit/test_po_auto_creation_validation.py
tests/unit/test_po_auto_close_on_full_receipt.py` and the wider procurement/workflow suite,
all passing except pre-existing gaps noted in section 6).

## 1. Admin-configurable PO (and other) email templates

**Current state, confirmed by reading the code:** `backend/app/templates/email/
templates_catalog.json` is a 24-entry, 197KB JSON file cataloging templates for every
lifecycle email in the system (PR approval, PO dispatch, PO change, receipt confirmation,
receipt discrepancy, invoice exception/approved, payment completed/failed, supplier
registration/requalification/disqualification, RFQ invitation, etc.) — subject, HTML, text,
variables, and a `tenant_overridable: true/false` flag per entry. **None of this is wired
to anything.** `EmailService.load_template()` (`backend/app/services/email_service.py`)
only reads flat `.html` files by name from the same directory — as of this prompt there are
5 real files: `welcome_email.html`, `password_reset_email.html`,
`order_confirmation_email.html`, `approval_required.html`, and `po_dispatch_email.html`
(the last one added this session, ported from the catalog's `po_dispatch_v1` entry — see it
as the reference pattern for porting the rest). There is no `EmailTemplate` DB table, no
admin router, no admin UI anywhere — confirmed via grep, zero matches for `EmailTemplate`
or `email_template` outside the dead catalog file.

**Build:**
- A new `EmailTemplateOverride` model (migration required): `id`, `tenant_id` (nullable —
  global default vs. tenant-specific), `email_type` (matches the catalog's `email_type`,
  e.g. `po.dispatch`), `subject_override` (nullable), `html_override` (nullable),
  `footer_override` (nullable), `branding_logo_url` (nullable), `is_active`, timestamps.
  Only store what's actually overridden — fall back to the catalog default when a field is
  null, don't force admins to redefine a whole template to change one line.
- `EmailService.send_email` (or a thin wrapper around it) should check for an active
  override matching `email_type` (+ tenant) before falling back to `load_template()`. Keep
  the redirect pipeline (`apply_redirect`) exactly as-is — overrides only change content,
  never delivery/redirect behavior.
- Admin router: `GET/PUT /admin/email-templates/{email_type}` (list all catalog entries
  merged with any active override so the UI always has something to show; PUT upserts the
  override). Gate with the same `_require_admin` pattern used in
  `backend/app/routers/workflow.py`.
- Admin UI: new page under `frontend/app/dashboard/admin/` (follow the existing admin
  section pattern — see `admin/templates`, `admin/master-data` for the established
  look/nav wiring) listing templates by module (the catalog's `module` field groups them:
  "PR", "PO", "Receipts", "Invoices", "Supplier Management", etc.), with a form for
  subject / body / footer / branding logo / instructions per the user's spec ("Admin can
  configure PO email template: subject, body, footer, branding, instructions").
- Scope to the PO dispatch template only if time-constrained (it's the one with a live send
  path today); the model/router/UI should still be built generically against
  `email_type` so wiring up the other 23 templates later is just "point another sender at
  it," not a redesign.

## 2. More supplier seed data

**Current state:** `backend/scripts/` has seed scripts for workflow definitions, supplier
*types*, supplier request templates, registration questionnaires, and the approver matrix —
but no general supplier seed script. Grep confirms zero `seed_supplier` matches beyond
`seed_supplier_request_template.py` and `seed_supplier_types.py`, neither of which creates
`Supplier` rows.

**Build:** `backend/scripts/seed_suppliers.py`, idempotent (check `external_supplier_code`
or name before inserting, same pattern as `three_way_policy` fixture-style upserts used
throughout the test suite). Cover a realistic spread: 15-20 suppliers across several
categories/commodities (IT hardware, office supplies, professional services, facilities,
raw materials — match whatever `category`/`commodity` values the existing
`CommodityMatchingPolicy`/catalog data already uses, don't invent a new taxonomy). Every
seeded supplier needs `is_active=True` and a real-looking `contact_email` — this session
added a hard PO-auto-creation validation gate
(`app/services/procurement_workflow.py::_po_creation_blockers`) that blocks PO creation
outright when the supplier has no email or is inactive, so seed data without these will
silently produce "exception" PRs instead of demoable PO flows.

## 3. Static catalog with images for PR quick-add

**Current state:** no `Catalog`/`CatalogItem` model exists anywhere in
`backend/app/models/` — confirmed via grep. This is a genuine net-new feature, not a gap in
something half-built.

**Build (spec explicitly says minimal — "2-3 items"):**
- `CatalogItem` model: `id`, `name`, `description`, `image_url`, `unit_price`, `currency`,
  `supplier_id` (FK), `category`, `commodity`, `is_active`. Migration + CRUD + a simple
  `GET /catalog` list endpoint (no admin CRUD UI needed for v1 — 2-3 items can be seeded
  directly like section 2).
- Frontend: a small catalog grid/card component (thumbnail, price, supplier name,
  category badge, "Quick add" button) somewhere reachable from PR creation — the natural
  spot is inside `frontend/app/dashboard/requisitions/new/page.tsx`'s Step 2 (Line Items),
  as an alternative to the manual line-item form. "Quick add" should call
  `addRequisitionLineItem` with the catalog item's fields pre-filled (description,
  unit_price, category, commodity, and — important, see section 1's note on GL validation —
  `account_code` if the catalog item has a default one, otherwise the PR will hit the same
  auto-validation gate at approval time).
- Use placeholder/stock image URLs (e.g. a public placeholder image service or 2-3 files
  committed under `frontend/public/`) — don't build image upload/storage for this pass.

## 4. Reports & Analytics

**Current state:** `backend/app/routers/analytics.py` already exists and is live — it has
dashboard metrics, spend analytics, supplier analytics, contract analytics, a spend
forecast, a spend cube, and savings records. **Check each of the 4 requested reports
against what's already there before building from scratch:**
- **Supplier performance scorecard** — `supplier analytics` may already cover most of
  this; read `get_supplier_analytics` (or equivalent) in `analytics.py` and its frontend
  consumer before adding a new endpoint. Likely just needs extending, not a new report.
- **PO aging** — not covered by anything above (all existing endpoints are spend/contract
  focused, not lifecycle-age focused). New: age = now − `created_at` (or `approved_at`)
  bucketed (0-7/8-14/15-30/30+ days), grouped by current `lifecycle_status`, for POs not
  yet `closed`/`cancelled`.
- **Approval bottleneck report** — check `backend/app/services/approval_audit.py`
  (`record_approval_event`, `record_task_sla_metric` — both already called from
  `complete_task` in `crud/workflow.py`) and whatever reads `ApprovalEvent`/SLA metric rows
  today (grep for `SlaDefinitionEntry`, `ApprovalAnalytics` in
  `frontend/lib/types.ts` — an `ApprovalAnalytics` type already exists, check whether its
  backing endpoint already ships bottleneck data before building new).
- **Exception dashboard** — new. This session's PO auto-creation work introduces
  `ProcurementRequisition.lifecycle_status = "exception"` with a
  `ProcurementAuditEvent(action="purchase_order:creation_blocked", details={"reasons":
  [...]})` row recorded alongside it (see `_po_creation_blockers` in
  `app/services/procurement_workflow.py`) — that's the exact data source this report
  needs. A simple list/table of requisitions in `exception` status with their blocker
  reasons and a resolve/retry action (re-running `auto_create_po_from_requisition` once the
  underlying issue — e.g. missing supplier email — is fixed) covers the spec's ask.

Build each as its own `GET /analytics/...` endpoint (extend the existing router, follow its
established response-shape conventions) + a frontend view under
`frontend/app/dashboard/spend/` (where the existing analytics pages already live) or a new
`admin/reports` section if these are meant to be admin-only — check with the user which fits
better before deciding.

## 5. Remaining PR UX/backlog items (lower priority — do sections 1-4 first)

Grab-bag from the original spec, none started:
- **3-click minimum PR creation.** Current `requisitions/new/page.tsx` is a 3-*step* wizard
  (Header → Line Items → Summary & Submit), not literally 3 clicks — a real minimum-click
  flow (per spec: "1. Select item, 2. Select supplier, 3. Submit PR") only becomes possible
  once section 3's catalog quick-add exists (select catalog item → confirm/select supplier
  if not already defaulted on the item → submit). Build this as a distinct fast-path
  entry point, not a replacement for the full wizard (which is still needed for non-catalog/
  custom requisitions).
- **Auto-fill**: ship-to, cost center, GL code, delivery date, UOM, price — mostly falls
  out of section 3 (catalog items carry price/GL) plus a "default ship-to per requester"
  lookup, which doesn't exist yet (`ProcurementRequisition` has no ship-to field at all —
  see the note in `_po_creation_blockers`'s docstring from this session's commit).
- **PR preview before submission** — a read-only summary step already exists (wizard Step
  3, "Summary & Submit") — check whether this already satisfies the spec's ask before
  building a separate preview modal.
- **PR copy, create-on-behalf, emergency PR, delay-until** — `is_emergency` and
  `delay_until` are already real columns on `ProcurementRequisition` and already captured
  by the new-PR form (confirmed in `requisitions/new/page.tsx`); "PR copy" and "create on
  behalf" (a different `requested_by` than the logged-in user, admin/procurement-agent only)
  are not built — check for a `requested_by` override capability before assuming it needs a
  new field (the column already supports any user id).
- **Internal-only vs. supplier-visible attachments** — `ProcurementAttachment` exists
  (`models/procurement.py`) with no visibility flag; would need one new nullable/defaulted
  boolean column + migration.
- **Invoice reconciliation details + price mismatch alerts** — check
  `backend/app/routers/procurement.py`'s invoice-matching endpoints and
  `crud/procurement.py::match_invoice` first; 3-way matching and exceptions already exist
  (Invoice Matching Phase 4 per project history) — this may be a frontend display gap
  (surfacing existing match/exception data on the invoice detail page) rather than a
  backend gap. Verify before building new matching logic.
- **Supplier import tool, templates, category presets, communication history** — no
  existing infrastructure; scope as its own follow-up prompt if picked up, it's sizable.
- **Inline validation, auto-suggest GL/category/supplier, auto-save draft, fast search,
  keyboard shortcuts, mobile PR + swipe actions, AI duplicate-PR/price-anomaly detection** —
  none started; treat as their own individually-scoped passes, this is too broad to batch
  into one implementation session.

## 6. Known pre-existing test gaps (do not attempt to fix as part of this prompt)

Confirmed via this session's test runs, unrelated to any of the above:
- `test_matching_policy_auto_receipt.py::test_unconfigured_commodity_still_requires_manual_receiving`,
  `test_receipt_workflow.py::test_post_auto_creates_balance_draft_that_blocks_manual`,
  `test_goods_receipts.py::test_goods_receipt_line_item_status_rollup_and_over_receipt_exception`,
  and `test_end_to_end_procurement.py` (at the "manually receive" step) all hit the same
  "one open receipt per line" guard in `create_goods_receipt`
  (`crud/procurement.py`) in ways their fixtures don't account for — the guard conflicts
  with `auto_create_draft_receipt_for_po`'s automatic draft-receipt scaffolding.
- `test_procurement_workflow.py::test_complete_task_rejects_self_approval_for_requisition`
  calls `complete_task` with `db=None` and hits `AttributeError` on `db.flush()` before
  reaching the self-approval check it's actually testing.
- `test_workflow_blocked_approval.py::test_retry_blocked_instance_reruns_and_blocks_again`,
  `test_workflow_definition_versioning.py::test_editing_definition_versions_without_touching_old_instances`.

If you end up touching `create_goods_receipt`'s receipt-guard logic for any reason above,
this is the natural moment to also fix the first group — otherwise leave all of these alone,
they're out of scope for this prompt.

## 7. Definition of done (per section you pick up)

- Migration written and applied where a new model is introduced (model → schema → crud →
  router → migration → tests, the established project pattern).
- New/changed backend endpoints covered by at least one integration test using the real
  `client`/`db_session` fixtures (see `tests/integration/test_po_auto_creation_validation.py`
  from this session for the current house style: real HTTP calls through the FastAPI test
  client, real in-memory SQLite, no mocking of the code under test).
- Frontend changes reviewed by hand for balanced JSX/TS (the sandbox this was drafted in
  cannot run `tsc`/`next build` — confirm build cleanliness on your own machine before
  considering a section done).
- Existing tests still pass (`pytest tests/` at repo root, not `backend/tests/` — see
  project pytest.ini) aside from the pre-existing gaps listed in section 6.
- Commit with a message that states which section(s) of this prompt were completed, so the
  next session (Claude or otherwise) can tell what's still open at a glance.
