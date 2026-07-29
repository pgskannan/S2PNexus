# Copilot Prompt — PR-to-PO Defect Fixes

Written 2026-07-29, against the PR/PO functional spec provided by the user (full
Ariba-style spec — creation, validation, workflow, auto-PO, ERP sync, AI, reporting).
**Do not build the whole spec.** Sections 6 (Reporting), 7.2 (ERP sync to
SAP/Oracle/NetSuite/Dynamics), 8 (AI suggestions/risk scoring), catalog auto-fill,
duplicate-PR detection, contract-price validation, and preferred-supplier enforcement are
explicitly out of scope for this pass — see [[project_s2pnexus_xprize_focus_llm_parked]]
in spirit: this project is 18 days from the XPRIZE deadline and needs the core P2P flow
to be correct and demoable, not the full enterprise feature set. This prompt is scoped to
real defects found by auditing the current code against the spec — confirmed by reading
`backend/app/models/procurement.py`, `crud/procurement.py`, `routers/procurement.py`,
`crud/workflow.py`, and the frontend requisition/convert-to-po pages.

## 1. Headline defect: PO creation is 100% manual, spec requires automatic on final approval

Spec 2.4.1: "If PR is fully approved → PO auto-created." Today, `_run_from_step` in
`backend/app/crud/workflow.py` (~line 119-127) only flips `instance.status = "completed"`
when a workflow instance finishes — it never calls any procurement code. PO creation is
only reachable by a user manually opening `/dashboard/requisitions/{id}/convert-to-po`
and clicking a button (`frontend/app/dashboard/requisitions/[id]/convert-to-po/page.tsx`).
There is no automatic trigger anywhere.

**Fix:** in `crud/workflow.py`, when `_run_from_step` (or `complete_task`, wherever the
instance transitions to `"completed"`) finishes an instance whose `entity_type ==
"requisition"`, call a new hook —
`app/services/procurement_workflow.py::auto_create_po_from_requisition(db, requisition_id,
started_by)` — instead of requiring a manual click. Keep this entity-type-dispatched
(don't hardcode procurement logic into the generic workflow engine); a small
`if instance.entity_type == "requisition": await auto_create_po_from_requisition(...)`
right after the instance is marked completed is enough. Leave the manual "Convert to PO"
button in place as a fallback/override path (e.g. for requisitions with no configured
workflow, which still use the `evaluate_approval_requirement` fallback), but the primary
path must be automatic once a workflow-driven approval completes.

## 2. Second-order defect: PO creation trusts the client, not the requisition

Spec 2.4.1: the PO "must inherit" supplier, line items, contract ID, ship-to address,
delivery date, GL/cost center, attachments from the PR. Today,
`convert_requisition_to_purchase_order` (`routers/procurement.py` ~line 245-264) only
uses the requisition to 404-check it exists, then calls `create_purchase_order`
(`crud/procurement.py` ~line 233-394) with a fully client-supplied `PurchaseOrderCreate`
payload — `supplier_id` is a required field on that payload
(`schemas/procurement.py` ~line 148) that the *client* provides. The frontend happens to
pre-fill the form from the requisition (`convert-to-po/page.tsx` lines 70-76), but that's
a UI convenience, not a server-side guarantee — a raw API call could create a PO with an
unrelated supplier or line items.

**Fix:** add a server-side derivation step. When `auto_create_po_from_requisition` (or the
manual convert endpoint) builds the PO, it should read `supplier_id`, line items,
`need_by_date`, ship-to default, and GL/account-code fields directly off the
`ProcurementRequisition`/`ProcurementRequisitionLineItem` rows rather than accepting them
as arbitrary client input. Keep the manual endpoint able to accept *overrides* (ship-to,
incoterms, payment terms — things genuinely decided at PO time per the existing PO pages
work), but supplier and line items should be sourced from the requisition, not
re-specified by the caller.

## 3. Delay Until is a dead field

Spec 2.1.1: if `Purchase Delay Until` is set, PO creation should be deferred until that
date. `delay_until` is a real column (`models/procurement.py` ~line 50) and the frontend
captures it (`requisitions/new/page.tsx` lines 57, 121, 353-363), but it's never read
anywhere in `crud/procurement.py` or `routers/procurement.py` — grep confirms zero usage
outside the model/schema/migration.

**Fix:** in `auto_create_po_from_requisition` (from #1), check `requisition.delay_until`.
If it's set and in the future, don't create the PO yet — leave the requisition in an
"approved, pending PO creation" state instead. This codebase has no background scheduler
(same constraint noted for workflow escalation — see `escalate_overdue_tasks` in
`crud/workflow.py`, which is a sweep meant to be called periodically or on-demand). Mirror
that exact pattern: add `process_deferred_po_creation(db)` that finds approved
requisitions whose `delay_until` has passed and no PO yet exists, and creates their POs;
expose it as `POST /procurement/requisitions/process-deferred-pos`, callable on-demand
alongside the existing `/escalate` sweep. Do not build a real scheduler/cron — that's
infra work outside this scope.

## 4. Governance gap: nothing stops a requester approving their own PR

Spec 2.3.3: "Creator cannot approve their own PR." `complete_task` in `crud/workflow.py`
(~line 282-329) has no check comparing the acting user to the requisition's creator —
confirmed via grep, zero matches for any self-approval guard anywhere in the workflow
engine.

**Fix:** two layers, both scoped to `entity_type == "requisition"` so the generic engine
isn't polluted with procurement-specific logic:
- **Assignment time** — in `start_requisition_approval_workflow`
  (`services/procurement_workflow.py`), when starting the instance, drop the requisition's
  `requested_by` from any `approvers` list if the workflow definition happens to include
  them (defense in depth, cheap to add).
- **Completion time** — in `complete_task`, after loading the `instance`, if
  `instance.entity_type == "requisition"`, look up the requisition's `requested_by` and
  raise `ValueError("Requisition creator cannot approve their own request")` if
  `actor_id == requested_by`. This mirrors the existing pattern of raising `ValueError` for
  invalid transitions, which the router already converts to a 400
  (see `feedback_starlette_cors_on_500` — never let this surface as an unhandled 500).

## 5. Validation gap: spec's "mandatory" line-item fields are optional in the schema

Spec 2.1.2/2.2 says item description, quantity, UoM, price, category, GL code, cost
center, and delivery date are all mandatory per line, with inline validation. Today
`ProcurementRequisitionLineItemCreate` (`schemas/procurement.py` ~line 87-95) only
requires `description` and defaults `quantity` to 1 — `unit_price`, `category`, and
`account_code` are all `Optional`. The frontend explicitly allows blank rows to be
skipped ("Leave a row's description blank to skip it",
`requisitions/new/page.tsx` line 427).

**Fix (validation only, no new columns — see #6 for the schema gaps):** make
`unit_price` and `category` required (non-`Optional`, `gt=0` on price) on
`ProcurementRequisitionLineItemCreate`, matching what the field already stores. Add
matching frontend inline validation (red-asterisk equivalent + inline error, consistent
with the rest of the app's form patterns) rather than silently dropping incomplete rows.
Leave `account_code` optional for now — see #6, cost center isn't really separated from
GL code in the current data model, that's a bigger fix.

## 6. Lower priority — real schema gaps (do only if #1-5 are done with time to spare)

These are genuine spec gaps, not just validation gaps, and need a migration:
- No `unit_of_measure` field on `ProcurementRequisitionLineItem`.
- No per-line `delivery_date` (only a header-level `need_by_date` on the requisition).
- No per-line `contract_id`.
- No `supplier_location_id` or supplier-contact field on the requisition header.
- No ship-to address field on the requisition at all (only exists on PO, set at convert
  time) — spec wants a PR-level default with override.
- The PR creation form (`requisitions/new/page.tsx`) has no supplier field at all, despite
  `supplier_id` existing on the backend schema.

If you pick any of these up, treat them as a normal migration (model → schema → crud →
router → migration → tests, per the established project pattern) and keep the PR form's
supplier field wired to the same supplier picker already used on the PO pages — don't
build a new one.

## 7. Explicit non-goals for this pass

Catalog vs. non-catalog auto-fill (spec 2.1.3), duplicate-PR detection, contract-price
validation, budget-availability check at PR creation time (budget is already enforced at
PO approval via `_check_po_budget_on_approval`, which is sufficient for the demo),
preferred-supplier enforcement, AI suggestions (category/supplier/GL/description/price),
supplier risk scoring, price-anomaly detection, all reporting (2.6), all ERP integrations
beyond what's already live (Vertex AI / Cloud Run), multi-currency, multi-ship-to. Several
of these are explicitly answered "NO" in the spec's own Section 9 (multiple ship-to,
multiple currencies) — don't build what the spec itself says not to.

## 8. Definition of done

- Approving the final step of a requisition's workflow instance creates a PO
  automatically, with no manual click required, unless `delay_until` is set in the
  future (in which case it's created by the deferred-PO sweep once that date passes).
- The created PO's supplier and line items are derived from the requisition server-side,
  not accepted verbatim from the client.
- A user cannot approve a workflow task on a requisition they created — verified by an
  integration test that asserts `complete_task` raises when `actor_id == requested_by`.
- Line items with a missing price or category are rejected at the API level with a 422,
  not silently accepted or silently skipped.
- Integration tests cover: auto-PO-on-approval (happy path), deferred PO via
  `delay_until`, and the self-approval rejection. Existing PR/PO/workflow tests still
  pass unmodified.
- `tsc --noEmit` and `next build` clean on the frontend if any frontend files changed.
