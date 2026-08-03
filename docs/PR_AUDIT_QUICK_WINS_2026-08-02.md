# Purchase Requisition Module — Gap Audit vs. Functional Spec

**Date:** 2026-08-02 | **Spec:** PR Functional Specification v1.0 (Copilot, 02-Aug-2026) | **Method:** code audit of `backend/app/{models,crud,routers,schemas}/procurement.py` and related modules, plus `frontend/app/dashboard/requisitions/*`

## Summary

The PR module is further along than the spec makes it look — approval workflow, budget enforcement, receipts, and PR→PO automation are genuinely built and deployed. The real gap isn't missing engines, it's **unwired plumbing**: several capabilities exist fully in the backend (preferred-supplier scoring, budget check, PO line fields, approval-status filtering) but were never connected to the PR creation/detail UI. Those are the cheapest wins available — no new data model, no migration, just wiring.

The genuine gaps (contract linkage, department/cost center, catalog integration, ERP sync, AI suggestions, attachments) require real backend work of varying size.

## Quick Wins (ranked by effort, cheapest first)

**1. Expose existing PO line item fields in the API response.**
`PurchaseOrderLineItem` already has `unit_of_measure`, `tax_code`, `tax_amount`, `need_by_date`, `promised_date`, and `notes` — but `PurchaseOrderLineItemResponse` strips them out. Add the fields to the schema; no migration needed. Closes part of 5.3 (PR/PO line fields) for POs immediately.

**2. Add `approval_status` as a query filter on `GET /requisitions`.**
The field already exists on the model and is returned in responses, it's just not filterable. Add the query param + frontend filter chip. Closes part of 5.5 (advanced search).

**3. Surface the budget check live on the PR draft screen.**
`GET /budget/check` already exists and is only called at PO-approval time. Call it as-you-type (or on save) in `new/page.tsx` so requestors see a budget-impact warning before submitting, not after. No backend work. Addresses 5.8 and part of 5.13 ("budget impact analysis").

**4. Surface preferred-supplier / risk score in the supplier picker.**
`services/preferred_supplier.py` computes a full composite score (qualification, performance, risk, spend tier) and `Supplier.current_risk_score` already exists — neither is consulted anywhere in the PR/PO supplier-selection flow. Add a badge/warning in the supplier dropdown ("risk score 85 — not preferred"). No backend work, high visibility for a "we already built this" win. Addresses most of 5.7.

**5. Build the attachments UI.**
The API (`POST /requisitions/{id}/attachments`, `ProcurementAttachment` model) exists but the frontend has zero attachment UI — the "new PR" page even tells users to add attachments on the detail page, which has no such section. Note: real file storage isn't wired either (`storage_key` is just a string column), so this is UI + storage wiring, not UI alone. Still closes a visibly broken promise to users and most of 5.4 (skip classification/versioning/preview for v1).

**6. Add PR-line fields: `line_number`, `unit_of_measure`, `delivery_date`, `notes`.**
Follows the established model→schema→crud→router→migration→tests pattern already used repeatedly in this codebase. Closes the rest of 5.3.

**7. Add PR header fields: `department`, `cost_center`, `justification` (mandatory).**
None of these exist on `ProcurementRequisition` today, which also blocks cost-center search (5.5) and cost-center-based approval routing (5.6). Same build pattern as #6, slightly larger since it also needs to feed into `WORKFLOW_FIELD_REGISTRY["requisition"]` and search filters to pay off fully.

**8. Copy/Duplicate PR.**
Missing entirely. A "duplicate" endpoint that clones a requisition + its line items into a new draft is a self-contained, moderate-effort feature with high requestor-convenience payoff (spec item 5.1).

**9. On-behalf-of / Proxy PR.**
Missing entirely — only `requested_by` exists. Needs a `requested_for_user_id` field, a "create on behalf of" picker (superuser/manager only), and workflow routing to still notify the actual requestor. Moderate effort, real value for admin/procurement-ops users.

## Notable gaps NOT recommended as quick wins (bigger lifts, sequence later)

- **Contract linkage on PR/PO** — `contract.py`/`contract_lifecycle.py` modules exist elsewhere in the app but nothing in `procurement.py` references them. Real integration work (contract-based item selection, contract price validation, contract compliance) depends on this being wired first.
- **Catalog integration** — no catalog item model exists at all.
- **ERP sync / webhooks** — explicitly out of scope today (documented in `services/receipt_workflow.py` as "not integrated").
- **AI-driven suggestions (5.13)** — current "auto-suggest" fields are plain typeahead, not ML. Real AI suggestion, duplicate-PR detection, and price-anomaly detection at PR time would need new model/service work. Per memory, LLM/agent feature work was explicitly parked in favor of P2P deployment and revenue priorities — worth checking whether that's still the case before scoping this.
- **PR-level risk scoring, PR aging report, cycle-time analytics** — no aggregation exists yet; moderate build once core fields (department/cost center) land, since those are natural report dimensions.
- **Field-level permission visibility / confidential attachments / SoD matrix** — currently only one hard-coded rule (creator can't approve own PR). A real permission/SoD framework is a bigger design effort, not a quick win.

## What's already solid (no action needed)

Approval workflow engine (parallel/conditional/escalation/delegation/auto-approval/matrix), budget enforcement at PO approval, PR→PO automation including delay-until and supplier acknowledgment, receipts lifecycle (auto-create, tolerance, auto-close), audit trail/versioning, and analytics (spend by category/supplier, forecasting, savings tracking) are all built and functioning. The spec's 5.6, 5.9, and most of 5.10 are effectively done already — worth reflecting that back to whoever is scoping against this document, since the spec reads as if none of it exists yet.

## Suggested sequencing

Items 1–5 above are all backend-complete wiring jobs — worth doing together as a single short sprint since none require a migration. Items 6–7 (new PR fields) naturally bundle since #7's payoff depends on #6-style plumbing being fresh. Items 8–9 (copy PR, proxy PR) are independent and can slot in whenever. Everything in the "bigger lifts" section should wait until contract linkage is scoped, since three of the gaps cascade from it.
