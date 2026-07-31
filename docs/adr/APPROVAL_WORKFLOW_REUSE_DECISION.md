# Unified Approval Workflow — Pre-Coding Reuse Decision

Applies the mandatory pre-coding check from the *Unified Approval Workflow
System Specification* (Section 3) before extending the workflow platform.

## Step 1 — Capability Discovery

| Capability (spec requires)        | Existing component                                     | Present? |
| --------------------------------- | ------------------------------------------------------ | -------- |
| Node graphs (ordered steps)       | `WorkflowDefinition.steps` + `crud.workflow._run_from_step` | ✅       |
| Conditional routing               | `condition` step type + `_evaluate_condition`          | ✅       |
| Human approval tasks              | `WorkflowTask` (one per approver, N-of-M via `required_approvals`) | ✅ |
| Escalation                        | `due_at` / `escalate_to` / `escalate_overdue_tasks`    | ✅       |
| Notifications                     | `Notification` model                                   | ✅       |
| Versioning (Draft/Publish/Archive)| `WorkflowDefinition.is_active` (binary only)           | ⚠️ partial |
| Approval audit trail              | Instance/Task rows (no dedicated APPROVAL_EVENT)       | ⚠️ partial |
| SLA tracking                      | `due_at` only (no SLA_DEFINITION / SLA_METRIC)         | ❌       |
| Rule-driven approver resolution   | hardcoded `approvers` in steps                         | ❌       |

There is no separate BPM microservice; the workflow engine lives in
`backend/app/crud/workflow.py` + `backend/app/models/workflow.py`, with a
drag-and-drop designer in the frontend (`/dashboard/workflow/definitions`).

## Step 2 — Reuse Decision

**reuse_existing_engine = true**

Justification: the existing engine already provides node graphs, conditional
routing, parallel human approvals, escalation, and notifications — the hard
parts of a BPM runtime. Rebuilding would duplicate that and break every domain
(requisitions, purchase orders, invoices, supplier registrations) already wired
to `start_workflow_instance` / `complete_task`.

Impact analysis: extension is additive and low-risk:
- New `ApproverSeed` master data (Section 1) — new table, no changes to existing.
- New rule engine (Section 2) — new service consulted when resolving approval
  step approvers; existing definitions with explicit `approvers` keep working.
- Definition status Draft/Publish/Archive (Section 3) — additive column
  (`status`), existing `is_active` preserved for compatibility.
- Approval audit + SLA (Section 4) — new `ApprovalEvent` / `SlaDefinition` /
  `SlaMetric` tables; hooks added at node start and task completion.

## Step 3 — Decision Record

- Decision: EXTEND existing engine (do not build a new one).
- Owner: S2PNexus backend team.
- Related modules: `app/crud/workflow.py`, `app/models/workflow.py`,
  `app/services/approval_rule_engine.py`, `app/services/approval_audit.py`,
  `app/models/approval.py`.
