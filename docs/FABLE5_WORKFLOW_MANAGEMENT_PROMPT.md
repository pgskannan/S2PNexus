# Prompt for Fable 5 — Dynamic Approval Matrix UI + Admin Console

Written 2026-08-01. Companion to `docs/WORKFLOW_MANAGEMENT_DESIGN.md` — read that first,
it explains *why* each phase is scoped the way it is. Paste the context block once, then
paste one phase at a time, in order. Phase 2 depends on Phase 1's `role_code` field
existing in the step schema round-trip. Phase 3 and 4 are independent of each other and
of Phase 2.

**Do not treat this as "build a workflow engine."** It already exists and is more capable
than the UI shows. Every phase below wires existing backend capability to a screen, or
adds a small, targeted backend endpoint next to code that already does 90% of the work.
If a phase seems to require a new data model or a new execution concept, stop and flag it
rather than inventing one — check `backend/app/models/approval.py` and
`backend/app/models/workflow.py` first, the field almost certainly already exists.

---

## Context for every phase (paste once)

You are extending S2PNexus, a Next.js (App Router) + FastAPI/SQLAlchemy async/Pydantic v2
codebase. Two engines already exist and must be reused, not duplicated:

1. **Workflow engine** — `WorkflowDefinition` (JSON `steps`, `entity_type`-scoped) →
   `WorkflowInstance` → `WorkflowTask`. Step types: `condition`, `approval`, `notification`,
   `auto`, `ai`. Execution logic: `backend/app/crud/workflow.py`, `_run_from_step()`.
   Schemas: `backend/app/schemas/workflow.py`. Frontend: `frontend/components/WorkflowCanvas.tsx`
   + `WorkflowNodeInspector.tsx`, used from `frontend/app/dashboard/workflow/definitions/page.tsx`.
2. **Approval matrix engine** — `ApproverSeed` (role/org-unit/amount-ceiling/category-scope/
   supplier-scope/primary-backup/delegation-window master data), `SlaDefinition`/`SlaMetric`,
   `ApprovalEvent` audit trail. Models: `backend/app/models/approval.py`. CRUD + resolution:
   `backend/app/crud/approval.py` (`resolve_approvers_for_context()` is the dynamic-routing
   function — read it before writing any new resolution logic). Router:
   `backend/app/routers/approval.py` (prefix `/approval`, plus a `workflow_router` at
   `/workflow` for publish/archive).

**Frontend conventions** (same as every other admin screen — see `admin/budgets/page.tsx`
and `admin/addresses/page.tsx` for the reference pattern):
- Pages under `frontend/app/dashboard/admin/...`, auto-wrapped by `admin/layout.tsx`'s
  sub-nav. Client-side admin gating: `user?.role === "administrator"`. Non-admins get a
  read-only view with a plain sentence explaining they can't edit — never a silently
  hidden page.
- `<div className="card">`, `btn-primary`/`btn-secondary`/`input-field`/`label` utility
  classes. Don't invent new component styling.
- All API calls through typed wrapper functions in `frontend/lib/api.ts`; new response/
  request shapes go in `frontend/lib/types.ts` next to the existing ones.
- Reuse `UserPicker` (`frontend/components/UserPicker.tsx`) for any user-selection field.

**Backend conventions**:
- Admin authorization: match each file's existing pattern (`routers/approval.py` — check
  what it uses today before adding new endpoints to it; don't mix styles within one file).
- Tenant scoping: `ApproverSeed`/`SlaDefinition`/`ApprovalEvent` all have `tenant_id` —
  every new query must filter by it the same way `list_approver_seeds()` already does.
- One Alembic head. If a phase needs a migration, check `alembic heads` before writing one.
- Async tests follow the repo's real-DB integration pattern (`tests/integration/`, plain
  `def test_x(): asyncio.run(...)`), not `pytest-asyncio` fixtures — this sandbox has a
  known `pytest-asyncio` version pin issue, use `0.23.8` if you need it at all.

---

## Phase 1 — Dynamic approval-node UI

Goal: an admin building a workflow can pick "resolve by role" instead of only "pick named
users," and see who that resolves to before saving.

**Already done (2026-08-01), read before starting**: `backend/app/crud/workflow.py`'s
`_evaluate_condition()` had a bug where amount-threshold conditions (`estimated_value >=
1000`) always evaluated false, because context stores Decimal fields as strings and the
comparison raised a silently-swallowed `TypeError`. Fixed via `_coerce_numeric()` — see the
function's docstring. `backend/scripts/seed_approver_matrix.py` seeds the full 8-role
`ApproverSeed` ladder (demo placeholder people) and publishes a working role-based
requisition `WorkflowDefinition` that exercises this end to end. Run that script first in
whatever environment you're testing against, so Phase 1's live-resolution preview has real
data to resolve against instead of an empty matrix.

**Backend**: none needed — `GET /approval/approvers/resolve` already exists
(`backend/app/routers/approval.py` line ~98). Confirm its query params match
`resolve_approvers_for_context()`'s signature (`role_code`, `amount`, `category`,
`supplier_id`, `tenant_id`) before wiring the frontend call — read the endpoint, don't
assume the prompt's paraphrase is exact.

**Frontend**:
1. `frontend/components/WorkflowCanvas.tsx` — add `role_code` to `WorkflowStepValue`
   (currently missing entirely, line 17-32) and to `mapStepsToValue`/`mapValueToSteps` so
   it round-trips through the JSON `steps` array like every other field already does. Add
   `Auto` and `AI Rule` to the palette buttons (line 205) and to `nodeColors` (line 42-48)
   with new step types `"auto"` / `"ai"` — the backend already executes both
   (`crud/workflow.py` lines 224-269), this is purely exposing what exists.
2. `frontend/components/WorkflowNodeInspector.tsx` — in the `step_type === "approval"`
   block (line 66), add a mode toggle: "Named users" (today's `UserPicker`, unchanged) vs.
   "By role" (new `<select>` over `APPROVER_ROLE_CODES` — mirror the list from
   `backend/app/models/approval.py` line 26 in `frontend/lib/types.ts` rather than
   hardcoding it twice). When role mode is selected, call the new `resolveApprovers()`
   wrapper (add to `lib/api.ts`, hitting `GET /approval/approvers/resolve`) with the
   selected role and, if available, the definition's typical amount/category, and render
   the resolved names read-only below the selector ("Currently resolves to: ..."). Add the
   same toggle to the `escalate_to` field for the same reason.
3. Add an `"ai"` step-type panel to the inspector editing `rules` — scope this to the
   literal shape `evaluate_rules()` in `backend/app/services/approval_rule_engine.py`
   actually reads (read that file first), not a speculative generic rule builder.

**Tests**: extend `tests/unit/test_procurement_workflow.py`-style unit test (or add
`tests/unit/test_workflow_role_resolution.py`) asserting a step with `role_code` set (no
explicit `approvers`) resolves via `resolve_approvers_for_context()` at instance-start time
— this path already exists in `crud/workflow.py` line 276-291, so the test should already
pass; add it as a regression guard, not to fix a bug.

---

## Phase 2 — Admin Dynamic Approval Matrix console

Goal: one admin screen listing/editing every `ApproverSeed`, replacing "call the API by
hand" as the only way to configure who approves what.

**Backend** — `backend/app/routers/approval.py` currently has `GET /approval/approvers`
(list) and `POST /approval/approvers` (upsert) but no way to fetch-then-edit a single
row's non-key fields without resending the full upsert payload, and no deactivate/delete.
**Important**: neither existing endpoint has any admin check today — both only depend on
`get_current_active_user`, so any authenticated user can currently write approval-matrix
master data. Don't copy that pattern forward. Add:
- `GET /approval/approvers/{id}` (single seed; any authenticated user may read, matching
  the existing list endpoint's gating — read-only is fine for non-admins)
- `PATCH /approval/approvers/{id}` (partial update, **admin-only** — reuse the existing
  upsert logic in `crud/approval.py`'s `upsert_approver_seed()` rather than writing a
  second update path; it already handles every field. Gate it the way `routers/budget.py`
  or `routers/org_structure.py` gates their write endpoints — check those files for the
  actual helper name/pattern in use, don't assume `_require_admin` exists here already)
- `DELETE /approval/approvers/{id}` → sets `active_flag = False` rather than a hard delete,
  **admin-only** (an `ApproverSeed` may be referenced by historical `ApprovalEvent`s —
  don't hard-delete master data with audit history pointing at it)

Flag, but do not silently fix as a drive-by: whether the *existing* `POST /approvers`
should also get an admin gate. That changes behavior for whatever's calling it today
(if anything) — call it out for explicit sign-off rather than bundling it into this phase.

**Frontend** — new `frontend/app/dashboard/admin/approvals/page.tsx` (register in the
admin nav/inventory the same way `admin/budgets` is registered):
- Tab 1, **Approver Matrix**: table of `ApproverSeed`s — role, org unit, amount ceiling +
  currency, category scope, supplier scope, primary/backup, delegation window, active —
  with create/edit (modal or inline, matching `admin/budgets/page.tsx`'s pattern) and a
  deactivate action calling the new `DELETE` endpoint. Add `listApproverSeeds`,
  `getApproverSeed`, `upsertApproverSeed`, `updateApproverSeed`, `deactivateApproverSeed`
  to `lib/api.ts`; add `ApproverSeed`/`ApproverSeedUpsert` types to `types.ts` matching
  `backend/app/schemas/approval.py` if it exists, or the model fields directly if not —
  check for an existing schema file before inventing shapes.
- Tab 2, **SLA Targets**: table of `SlaDefinition`s (document type, role, target duration,
  severity) with create via the existing `POST /approval/sla/definitions`, and inline
  breach-rate numbers pulled from `GET /approval/analytics` next to the matching row so an
  admin sees whether their targets are realistic.

**Tests**: real-DB integration tests for the three new endpoints — non-admin gets 403,
admin round-trips a create→get→patch→deactivate cycle, deactivated seeds are excluded from
`resolve_approvers_for_context()`'s `active_only=True` default (already true by
construction, just assert it).

---

## Phase 3 — Definition editing + minimal versioning

Goal: an admin can actually change a workflow definition that has already run once,
without it being frozen forever.

**Backend** — `backend/app/routers/workflow.py`: add `PUT /definitions/{id}` that, per
`docs/WORKFLOW_MANAGEMENT_DESIGN.md` Section 4.3, creates a **new** `WorkflowDefinition`
row (new `id`, same `entity_type`, incoming `steps`), archives the old one
(`set_workflow_definition_status(..., status="archived")`, already exists in
`crud/workflow.py` line 77), and leaves existing `WorkflowInstance` rows pointing at the
old `definition_id` untouched — confirm nothing in `_run_from_step()` re-reads the
definition by anything other than the instance's stored `definition_id` before assuming
this is safe (it currently reads `definition.steps` fresh each time via
`get_workflow_definition(db, instance.definition_id)`, so old instances keep running old
steps correctly — verify this against the actual code, don't take the paraphrase on
faith).

**Frontend** — `frontend/app/dashboard/workflow/definitions/page.tsx`: add an "Edit"
action per definition that opens the same canvas pre-populated with existing steps, and on
save calls the new `PUT` (via a new `updateWorkflowDefinition()` wrapper) instead of
`POST`. Show version history inline (list definitions grouped by `entity_type` + `name`,
newest first, with an Archived pill on superseded versions) rather than a flat list.

**Tests**: integration test that edits a definition with an existing completed instance,
asserts the old instance's `WorkflowInstanceResponse` is unchanged, and a newly-started
instance uses the new steps.

---

## Phase 4 — Wire Contract + Sourcing to the engine

Goal: "all documents of S2P" stops being aspirational.

Confirm current state first — `docs/WORKFLOW_MANAGEMENT_DESIGN.md` Section 3 states
Contract and Sourcing bypass the engine entirely based on a grep of
`backend/app/services/*_workflow.py`; re-verify against current `main` before starting,
since this may have changed since 2026-08-01.

If still true, replicate the exact pattern used four times already
(`supplier_workflow.py`'s `start_supplier_requalification_workflow` is the cleanest
reference): look up an active `WorkflowDefinition` for `entity_type="contract"` /
`"sourcing_event"`; if found, build a context dict and call `start_workflow_instance`; if
not found, fall back to existing behavior unchanged — zero regression for tenants with
nothing configured. Wire the call into whatever router currently handles contract/sourcing
lifecycle transitions (find via `grep -r "sourcing_event\|contract" backend/app/routers/`).

**Tests**: one integration test per entity type — start an instance, complete the
approval task, assert it reaches `completed`, mirroring the existing requisition/PO tests.

---

## Definition of done (all phases)

- An admin can configure "role X approves document type Y up to amount Z, in category
  scope W, with a named backup and a delegation window" entirely through the Approval
  Matrix screen — no direct API calls, no hand-typed JSON.
- The workflow canvas shows, for a role-based approval node, who it currently resolves to
  — not just the role name.
- Editing a workflow definition that has already run doesn't require deleting it first.
- Contract and Sourcing route through the same engine as every other document type (or,
  if Phase 4 finds this already done, that fact is confirmed and this file's Section 3
  premise is corrected).
- `tsc --noEmit` and `next build` clean on the frontend; existing workflow/approval tests
  pass unmodified — none of this changes engine execution semantics, only what's exposed
  and a small number of additive endpoints.
- Per `docs/WORKFLOW_MANAGEMENT_DESIGN.md` Section 4.5, do not start supervisor-cascade
  escalation or SoD enforcement as part of this batch — flag them as next, don't build
  them silently alongside these phases.
