# Copilot Prompt — Workflow Engine Rollout + Visual Designer

Written 2026-07-29. Companion to `docs/architecture/workflow-engine/*` (WF-001..WF-020),
which describes a full enterprise BPMN-style vision (policy/assignment/escalation/SLA
engines, AI nodes, plugin architecture, distributed Kubernetes runtime, sub-workflows,
loops). **Do not build that.** Those docs are marked `Status: Draft` / `Implementation
Status: Planned` and explicitly list most of that scope under "Future Enhancements." This
prompt scopes down to what's achievable in the current XPRIZE runway and reuses the real,
working engine that already exists.

## 1. What already exists (read this before writing any code)

`backend/app/models/workflow.py`, `backend/app/crud/workflow.py`, and
`backend/app/routers/workflow.py` implement a working, tested generic workflow engine:
`WorkflowDefinition` (named, `entity_type`-scoped, JSON `steps` list) →
`WorkflowInstance` (one run against one entity) → `WorkflowTask` (one row per approver).

Supported step types today: `condition` (branches on a context field with
eq/neq/gt/gte/lt/lte/in), `approval` (fans out one task per approver, supports N-of-M via
`required_approvals`, supports `escalate_after_hours`/`escalate_to`), `notification`
(creates an in-app `Notification` per recipient, template-formatted from context).
Escalation is a real sweep (`POST /escalate`, `escalate_overdue_tasks`) that reassigns
overdue tasks and notifies the escalation target. All of this works end-to-end — do not
rebuild it.

**The gap is wiring, not engine capability.** Today only `supplier` actually routes
through this engine (`backend/app/services/supplier_workflow.py`,
`start_supplier_requalification_workflow`): it looks up an active
`WorkflowDefinition` for `entity_type="supplier"`, and if none is configured, returns
`None` so the caller falls back to a plain status flip — it never assumes a definition
exists. Every other document type bypasses the engine entirely:

- **Requisition/PR** — `backend/app/services/procurement_workflow.py`,
  `evaluate_approval_requirement()`, is a hardcoded threshold (`estimated_value >= 1000
  or priority == "high"`). No `WorkflowDefinition` lookup, no configurability, no
  multi-step/multi-approver routing.
- **Purchase Order** — no workflow hook at all in `backend/app/routers/procurement.py`'s
  PO endpoints.
- **Goods Receipt over-receipt exceptions** — detected but not routed anywhere for
  approval.
- **Invoice matching exceptions** — `resolve_invoice_exception_endpoint` in
  `backend/app/routers/procurement.py` (~line 526) is a direct manual resolve with no
  assignment, no SLA, no escalation.
- **Contract / Sourcing (RFx)** — no workflow hook found.

**The designer gap:** `frontend/app/dashboard/workflow/definitions/page.tsx` is a raw
`<textarea>` where `steps` is hand-typed JSON. There is no visual editing, no palette, no
validation beyond what the backend rejects at save time. This is the literal blocker to
letting a non-engineer configure approval routing.

## 2. Non-goals (explicitly out of scope for this pass)

- Policy/Assignment/Escalation/SLA as separate services (WF-005/006/007/009) — the
  existing inline condition + approval + escalation-sweep model is sufficient for the
  document types in scope.
- New step types beyond `condition` / `approval` / `notification` (no Timer, Script,
  Webhook, Parallel/Merge-as-distinct-nodes, Loop, Sub-workflow, AI node) — parallel
  approval already works via multiple approvers on one `approval` step.
- Plugin architecture, event bus rework, BPMN import/export, simulation engine,
  multi-user collaborative editing, distributed/Kubernetes runtime.
- Business calendar / working-hours-aware SLA math — keep `escalate_after_hours` as a
  flat wall-clock offset.

If any of the above turns out to be truly required to close the demo gap, stop and flag
it rather than expanding scope silently.

## 3. Phase 1 — Wire every P2P document type to the real engine

Priority order matches the smoke-test chain in `docs/XPRIZE_SUBMISSION_PLAN.md` Section 3:
Requisition → Purchase Order → Goods Receipt exceptions → Invoice matching exceptions.
Contract and Sourcing are lower priority (add if time allows).

For each document type, replicate the `supplier_workflow.py` pattern exactly: look up the
active `WorkflowDefinition` for that `entity_type`; if found, build a context dict from
the entity's fields and call `start_workflow_instance`; if not found, fall back to the
existing hardcoded behavior unchanged so nothing regresses for tenants who haven't
configured anything yet.

1. **Requisition** (`entity_type="requisition"`, matching the frontend page's existing
   default) — in `procurement_workflow.py`, add a
   `start_requisition_approval_workflow()` alongside `evaluate_approval_requirement()`
   (keep the latter as the no-definition-configured fallback). Context should include at
   minimum `estimated_value`, `priority`, `department`, `requester_id`. Wire it in at the
   same call sites as `apply_procurement_transition_workflow` in
   `backend/app/routers/procurement.py`.
2. **Purchase Order** (`entity_type="purchase_order"`) — add the same pattern for PO
   approval/lifecycle transitions. Context: `total_amount`, `supplier_id`,
   `requires_budget_override` (from the existing hard/soft budget check in
   `crud/accounting_split.py` — a soft-budget warning is a good `condition` branch input).
3. **Goods Receipt** (`entity_type="goods_receipt"`) — route over-receipt detection into
   a workflow instance instead of just flagging it, so there's a real assignee and
   escalation path for the exception.
4. **Invoice matching exception** (`entity_type="invoice_exception"`) — replace/augment
   `resolve_invoice_exception_endpoint` so opening a match exception (2-/3-way variance)
   starts a workflow instance with an AP approver task, rather than being resolved by
   whoever happens to hit the endpoint. Keep the existing manual-resolve endpoint as the
   fallback path when no definition is configured.
5. **Contract** / **Sourcing** (`entity_type="contract"` / `"sourcing_event"`) — same
   pattern, lower priority.

For each: a migration is **not** required (no schema change, `WorkflowDefinition.
entity_type` is already a free-text string) — just seed one starter `WorkflowDefinition`
per entity type via a data script or the admin UI so the smoke test has something to
exercise, and add an integration test that starts an instance, completes the approval
task, and asserts the instance reaches `completed`.

## 4. Phase 2 — Visual Workflow Designer (replace the JSON textarea)

Scope this to the 3 real step types, not the 16-node palette in WF-014. Use
**React Flow** (`reactflow` on npm, MIT-licensed, works cleanly in Next.js/React 18,
no backend dependency) for the canvas — do not build a custom canvas from scratch.

Rebuild `frontend/app/dashboard/workflow/definitions/page.tsx` as:

- **Canvas** — React Flow graph. Nodes: `Start`, `Condition`, `Approval`,
  `Notification`, `End`. Edges represent the transition each step already encodes
  (`condition` steps' `on_true_next_step`/`on_false_next_step` indices become two labeled
  edges; `approval`/`notification` steps' implicit "next step" becomes one edge).
- **Palette** — a sidebar with the 4 node types (Condition/Approval/Notification/End),
  drag-to-add.
- **Property inspector** — a side panel bound to the selected node, editing exactly the
  fields the backend step schema already supports (`field`/`operator`/`value` for
  Condition; `approvers`/`required_approvals`/`escalate_after_hours`/`escalate_to` for
  Approval; `recipients`/`message_template` for Notification). Reuse
  `backend/app/schemas/workflow.py`'s step schemas as the source of truth for field names
  — don't invent new ones.
- **Validation** (client-side, before save) — every node reachable from Start, at least
  one path reaches End, Condition nodes have both branches wired, Approval nodes have
  ≥1 approver. Surface errors inline rather than only on the API's 422.
  On save, serialize the graph back to the same `steps: WorkflowStepCreate[]` JSON array
  the backend already accepts — **no backend schema changes needed for the designer
  itself.**
- Keep a "raw JSON" toggle for power users / debugging, but the canvas is the default view.
- Instance view (`frontend/app/dashboard/workflow/instances/[id]/page.tsx`) should
  highlight the current step on the same graph (read-only) rather than just listing task
  rows, so a judge watching the demo can see a workflow visually progress.

## 5. Files likely touched

Backend: `app/services/procurement_workflow.py`, `app/services/goods_receipt_workflow.py`
(new, mirrors `supplier_workflow.py`), `app/services/invoice_workflow.py` (new),
`app/routers/procurement.py`, plus one seed script (e.g.
`backend/scripts/seed_workflow_definitions.py`) for the starter definitions.
Frontend: `frontend/app/dashboard/workflow/definitions/page.tsx` (rewrite),
`frontend/app/dashboard/workflow/instances/[id]/page.tsx` (add graph view),
new `frontend/components/WorkflowCanvas.tsx`, `frontend/components/WorkflowNodeInspector.tsx`.
`package.json` — add `reactflow`.

## 6. Definition of done

- Requisition, PO, and at least one exception flow (goods receipt or invoice matching)
  start a real `WorkflowInstance` when a `WorkflowDefinition` is configured for that
  entity type, and fall back to today's behavior when none is configured — no regression
  for unconfigured tenants.
- A user can build a 3-4 step approval workflow (Start → Condition → Approval → End)
  entirely by dragging nodes on the canvas, with no hand-typed JSON, save it, and see it
  correctly drive a real instance through the existing runtime.
- Instance detail page shows the current step highlighted on the graph.
- Integration tests cover: starting an instance per newly-wired entity type, completing
  an approval task and advancing the instance, and the escalation sweep picking up an
  overdue task for at least one of the new entity types.
- `tsc --noEmit` and `next build` clean on the frontend; existing workflow tests still
  pass unmodified (the engine itself isn't changing).
