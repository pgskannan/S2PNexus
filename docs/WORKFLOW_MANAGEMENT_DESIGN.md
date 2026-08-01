# Workflow Management — Design: Beating Ariba/Coupa on Approval Routing

Written 2026-08-01. Scope: make S2PNexus's approval/workflow management genuinely
best-in-class — better UI on approval nodes, one admin surface for dynamic approval
routing across every S2P document type, and an architecture robust enough to carry that
without rework. Companion prompt: `docs/FABLE5_WORKFLOW_MANAGEMENT_PROMPT.md`.

**Relationship to the XPRIZE plan**: `docs/XPRIZE_SUBMISSION_PLAN.md`'s Section 3 (deploy
the 9 pending P2P migrations + one real end-to-end smoke test) remains the critical path
to the Aug 17 deadline. This work is scoped to run in parallel and should not block that
deploy. If a build session has to choose, the P2P deploy wins.

## 1. The real finding: the gap isn't the engine, it's the UI

The instinct for "build a world-class workflow engine" is to design a new one. That would
be a mistake here. `backend/app/models/approval.py` + `backend/app/crud/approval.py`
already implement a genuinely dynamic approval-matrix engine — role, org unit, amount
ceiling, category scope, supplier scope, primary/backup, delegation window, all evaluated
live per document. It is more capable than what the frontend lets anyone see or configure.
The actual gap is that almost none of it is wired to a screen. This is good news: the
highest-leverage work is UI and admin surface, not new backend architecture.

## 2. What's already live but invisible today

| Capability | Where it lives | Why it's invisible |
|---|---|---|
| Dynamic approver resolution by role + amount ceiling + category/supplier scope + delegation window | `ApproverSeed` model, `resolve_approvers_for_context()` in `backend/app/crud/approval.py` | No admin screen to create/edit seeds. Only a one-at-a-time upsert API (`POST /approval/approvers`) — no list-and-edit UI. |
| Per-document-type / per-role SLA targets with breach tracking | `SlaDefinition`/`SlaMetric` in `backend/app/models/approval.py`, `compute_sla_due_at()`/`evaluate_sla_breaches()` in `backend/app/services/approval_audit.py` | No admin screen. `POST /approval/sla/definitions` exists but nothing calls it from the UI. |
| Deterministic + AI rule evaluation that can auto-approve or suggest a role (`"ai"` step type) | `evaluate_rules()` in `backend/app/services/approval_rule_engine.py`, wired into `_run_from_step()` in `backend/app/crud/workflow.py` (lines 240-269) | The visual designer's palette (`WorkflowCanvas.tsx` line 205) only offers Condition/Approval/Notification — `"auto"` and `"ai"` step types aren't addable from the canvas at all. |
| Immutable approval audit trail with AI rationale/flags, SLA analytics (avg approval time, breach rate by node) | `ApprovalEvent`, `GET /approval/events`, `GET /approval/analytics` | No dashboard renders this. Judges/customers can't see it without hitting the API directly. |
| Definition lifecycle (draft/published/archived) | `POST /workflow/{id}/publish`, `POST /workflow/{id}/archive` (`backend/app/routers/approval.py`) | No lifecycle controls in the definitions UI — everything looks like one flat list. |
| Role-based approval routing (`role_code` on an approval step, resolved at runtime instead of hardcoded user IDs) | `WorkflowStep.role_code`, resolution logic in `crud/workflow.py` lines 271-296 | `WorkflowNodeInspector.tsx` has no `role_code` field — the canvas can only build steps with hand-picked named users, never dynamic role-based routing, even though the runtime fully supports it. |

## 3. What's genuinely missing (confirmed by reading the code, not assumed)

- **No way to edit a published definition.** `routers/workflow.py` has `POST`/`GET`/`DELETE`
  on `/definitions` but no `PUT`/`PATCH`. `delete_workflow_definition()` refuses to delete
  once a definition has execution history. Net effect: once a workflow has run once, it's
  frozen — you can only archive it and build a brand-new one from scratch, with no version
  linkage between old and new (no diff, no "instances on v1 keep running v1" semantics
  described in the Gold Standard spec Section 4.3).
- **No admin UI for the approval matrix at all** — the single biggest gap relative to
  Ariba/Coupa, where "who approves what, by amount/category/department" is the flagship
  admin screen. Today that data (`ApproverSeed`) can only be written via a raw API call.
- **Canvas is functionally a JSON-steps editor with a nicer skin**, not a real visual
  designer: no swimlanes, no parallel-branch visualization beyond multiple approvers on
  one node, no live "who would this actually route to" preview, no per-node SLA display.
- **Escalation is single-level and flat**: one `escalate_to` user, one `escalate_after_hours`
  number. No cascade (peer → manager → director → admin), no distinction between a
  personal delegate (covers day-to-day absence) and an organizational escalation chain
  (covers genuine non-response), no configurable stop conditions beyond the task being
  acted on.
- **No Segregation-of-Duties enforcement** — nothing stops a requester's manager from also
  being their AP approver on the same document; `complete_task()` only blocks the literal
  requester from approving their own requisition (`crud/workflow.py` line 456).
- **No admin gating on writing approval-matrix master data today.** `POST /approval/approvers`
  in `backend/app/routers/approval.py` (line 85) only depends on `get_current_active_user`
  — any authenticated user, not just admins, can currently create or overwrite an
  `ApproverSeed`. This isn't hypothetical: it's the literal dependency on that endpoint
  today. The new admin console (4.2) must not just add a UI on top of this; the endpoints
  it uses need an actual admin check.
- **Contract and Sourcing document types are not wired to the engine** — only
  requisition/PO/goods-receipt/invoice/supplier route through `WorkflowInstance` today
  (confirmed by grep of `backend/app/services/*_workflow.py`). "All documents of S2P"
  isn't true yet; Contract and Sourcing bypass approval routing entirely.
- **`VALID_STEP_TYPES` in `models/workflow.py` (line 36) only lists `condition`/`approval`/
  `notification`**, even though `auto`/`ai` work fine at runtime — it's unused dead code,
  but worth fixing so it doesn't mislead the next person who reads it as a guardrail.

## 4. Target design

### 4.1 Approval node UI (the "better UI in approval nodes" ask)

Redesign `WorkflowNodeInspector.tsx`'s approval-step panel around a mode toggle, not a
single approvers list:

- **Explicit mode** (today's behavior) — pick named users via `UserPicker`. Keep this;
  small tenants with no org structure still need it.
- **Dynamic mode** (new) — pick a `role_code` from `APPROVER_ROLE_CODES`
  (`backend/app/models/approval.py` line 26: MANAGER, MANAGER_MANAGER, DEPT_HEAD, CFO,
  FIN_CTRL, PROC_HEAD, AP_HEAD, AP_PROCESSOR) instead of named users. Below the selector,
  call `GET /approval/approvers/resolve` live with a sample context (amount/category from
  the definition's `entity_type` defaults, or the actual document if editing from a
  document's approval tab) and render "This would currently route to: Jane Doe (primary),
  backup: John Smith" — so an admin sees the real resolution, not just a role name, before
  saving.
- **SLA row** — surface `escalate_after_hours` next to (not instead of) a read-only "Or
  inherits the SLA definition for `{document_type}` / `{role_code}` if one is configured"
  hint, with a link to the new SLA admin screen (4.2) if none exists yet.
- **Add `Auto` and `AI Rule` to the canvas palette** (`WorkflowCanvas.tsx` line 205),
  matching the two step types the backend already executes. The AI Rule node's inspector
  panel edits `rules` (today a raw `dict[str, Any]` — scope the v1 UI to the specific rule
  shape `evaluate_rules()` actually reads, don't invent a generic rule builder).
- **Escalate-to field** gets the same explicit/role-code toggle as approvers, for the same
  reason: today it's a single named user, which doesn't survive that person leaving.

### 4.2 Admin: unified Dynamic Approval Matrix console

New `frontend/app/dashboard/admin/approvals/` section (matches the existing
`admin/budgets`, `admin/addresses` pattern from the admin module), with two tabs:

- **Approver Matrix** — table over `ApproverSeed`: role, org unit, amount ceiling,
  category scope, supplier scope, primary/backup, delegation window, active. Add
  list/update/deactivate endpoints (today only upsert exists) so this is a real CRUD
  screen, not a form that only ever creates. This is the single screen that makes "admin
  should be able to see uniform dynamic approvals" true — one place to see and edit who
  approves what, for every document type, instead of it being buried per-definition JSON.
- **SLA Targets** — table over `SlaDefinition`: document type, role, target duration,
  severity, plus the breach-rate numbers from `GET /approval/analytics` shown inline so
  the admin can see whether their SLA targets are realistic, not just set them blind.
- Wire this into the Phase-0 admin inventory table (`docs/COPILOT_ADMIN_MODULE_PROMPT.md`)
  where "Delegated approvals" and "Custom enumerations" are currently listed `Coming soon`
  — this closes both, since `ApproverSeed`'s delegation window + backup approver *is* the
  delegation model, it just needs a screen.

### 4.3 Definition editing + versioning

Add `PUT /workflow/definitions/{id}` that creates a new `WorkflowDefinition` row (new
version), leaves running `WorkflowInstance`s bound to whatever `definition_id` they already
started on (no code change needed here — instances already store `definition_id`, not a
resolved copy of steps), and archives the prior version. Surface version history (created
date, who edited, active/archived) in the definitions list so an admin can see what changed
over time — this is the minimum version of Gold Standard spec Section 4.3, not the full
diff/compare UI.

### 4.4 Uniform coverage across all S2P documents

Wire Contract and Sourcing to the engine the same way `supplier_workflow.py` and
`procurement_workflow.py` already do it (look up an active `WorkflowDefinition` for
`entity_type="contract"` / `"sourcing_event"`, fall back to existing behavior if none
configured — zero regression risk, same pattern already proven four times over). Then the
admin Approval Matrix screen (4.2) and the Workflow Definitions list both filter by
`entity_type`, so an admin can genuinely see "every document type, one screen" — the
uniformity the ask is actually about.

### 4.5 Explicitly out of scope for this pass

Pulled from `docs/ProcuraAI_Workflow_Engine_Gold_Standard_Spec_v3.docx` (the fuller vision
this design draws from) and deliberately deferred:

- Multi-level supervisor-cascade escalation (spec Section 6.13) — real and valuable, but
  a second escalation mechanism on top of what exists is a bigger lift than this pass;
  flag as the top Phase-2 candidate.
- Segregation-of-Duties rule engine (spec Section 5.5) — needs its own rule model; don't
  bolt it onto `ApproverSeed`.
- Saga-pattern resilience for side effects, business-calendar-aware SLA math, generic
  ERP adapter layer, event bus, chaos testing, multi-region data residency — all
  legitimate "Gold Standard" tier per the spec's own phased roadmap (its last phase, not
  MVP/Phase 2), not needed to make the UI honest about what already runs.
- A custom rule-expression language / sandboxed guard DSL (spec Section 4.4) — the
  existing `_OPERATORS` comparison set in `crud/workflow.py` is sufficient for now.

## 5. Why this reads as "better than Ariba/Coupa" in a demo

Ariba users' most common complaint is inflexibility; Coupa users' most common complaint is
that approval chains become unmanageable to configure (see research below). The design
above targets exactly that gap: one screen where a non-engineer admin sets "invoices over
$10k in Facilities route to the Facilities Director, with automatic fallback to their
backup during a configured leave window" and can immediately see, on the canvas, who that
resolves to today — not a JSON blob, not a support ticket to IT. That's a concrete,
demoable differentiator, not a marketing claim.

Sources: [Best Vendor Onboarding Software 2026](https://www.zamp.ai/blogs/best-vendor-onboarding-software-in-2025-sap-ariba-vs-coupa-vs-zip-vs-ai-agents), [Zapro vs Coupa vs SAP Ariba VMS Comparison 2026](https://zapro.ai/vendor-management/zapro-vs-coupa-vs-sap-ariba/), [SAP Ariba vs Coupa Independent Comparison](https://blog.teem.finance/product-comparison-report-sapariba-vs-coupa/)

## 6. Phased roadmap for this pass

| Phase | Scope |
|---|---|
| 1 | Approval-node UI: dynamic role-code mode + live resolution preview + SLA hint (4.1) |
| 2 | Admin Approval Matrix + SLA Targets console (4.2) |
| 3 | Definition edit/versioning endpoint + UI (4.3) |
| 4 | Wire Contract + Sourcing to the engine (4.4) |
| Later, explicit sign-off required | Supervisor-cascade escalation, SoD engine (4.5) |

See `docs/FABLE5_WORKFLOW_MANAGEMENT_PROMPT.md` for the phase-by-phase build prompt.

## 7. Already done, ahead of the UI work (2026-08-01)

Two things were built while preparing seed data for this design, both prerequisites for
Phase 1 actually working correctly:

- **Fixed a real bug in `_evaluate_condition()`** (`backend/app/crud/workflow.py`): context
  values built from ORM entities are stringified before storage (no Decimal/UUID encoder on
  the JSON column), so a condition like `estimated_value >= 1000` was comparing the string
  `"1500.00"` against the int `1000` — Python raises `TypeError` on that comparison, which
  was being silently caught and treated as `False`. Every amount-threshold condition always
  took the false branch, regardless of the real amount. Added `_coerce_numeric()`, scoped to
  the four ordering operators only (`eq`/`neq`/`in` untouched, since those are also used for
  non-numeric fields). Regression tests in `tests/unit/test_workflow_condition_coercion.py`.
- **`backend/scripts/seed_approver_matrix.py`** — seeds the full 8-role `ApproverSeed`
  ladder (placeholder demo people, clearly labeled, swap for real staff later) and publishes
  a real amount-tiered requisition `WorkflowDefinition` (under $1,000 auto-approved,
  $1,000+ routes to `MANAGER`, $10,000+ routes to `MANAGER` then `DEPT_HEAD`) that resolves
  approvers dynamically by role instead of hardcoded user IDs — the first definition in the
  repo that actually exercises role-based resolution end to end. Direct-DB script, no
  credentials involved; see the script's docstring for how to run it.
