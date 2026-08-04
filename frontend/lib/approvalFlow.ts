import { listUserDirectory } from "@/lib/api";
import type { WorkflowInstance, WorkflowTask } from "@/lib/types";
import type { ApprovalStep, ApprovalStepStatus } from "@/components/ApprovalFlowDiagram";

// S2PNexus's generic workflow engine fans out one WorkflowTask per parallel
// approver on a step (see backend/app/crud/workflow.py::_run_from_step), and
// only creates tasks for a step once execution actually reaches it. The
// Ariba-style diagram wants one ApprovalStep card per approver in document
// order, including steps that haven't been reached yet (shown as "Waiting")
// -- this maps one onto the other.

type ConditionOp = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "in";

/** Client-side mirror of the backend condition evaluator
 * (crud/workflow.py::_evaluate_condition) so the diagram can show which
 * branch of a condition is actually active for this instance. Uses the
 * instance's context snapshot (numbers stored as strings), so numeric
 * comparisons coerce like the backend does. */
function evaluateCondition(step: Record<string, unknown>, context: Record<string, unknown>): boolean {
  const field = typeof step.field === "string" ? step.field : "";
  const op = (typeof step.operator === "string" ? step.operator : "eq") as ConditionOp;
  const actual = context[field];
  const expected = step.value;
  try {
    switch (op) {
      case "eq":
        return actual == expected;
      case "neq":
        return actual != expected;
      case "gt":
        return Number(actual) > Number(expected);
      case "gte":
        return Number(actual) >= Number(expected);
      case "lt":
        return Number(actual) < Number(expected);
      case "lte":
        return Number(actual) <= Number(expected);
      case "in":
        return Array.isArray(expected) ? expected.includes(actual) : false;
      default:
        return false;
    }
  } catch {
    return false;
  }
}

/** Walk a definition from step 0 (following conditions against the instance's
 * context snapshot and parallel-group fan-out) and return the set of step
 * indices execution will actually visit. Approval steps outside this set are
 * on a branch that won't trigger for this document -- shown as "Not in path"
 * instead of a misleading "Waiting". Mirrors backend
 * `_continue_after_step` so Yes/No condition arms don't chain into each other. */
function conditionSiblingArm(
  definitionSteps: Array<Record<string, unknown>>,
  stepIndex: number
): { sibling: number; merge: number } | null {
  for (const step of definitionSteps) {
    if ((typeof step.step_type === "string" ? step.step_type : "") !== "condition") continue;
    const trueT = typeof step.on_true_next_step === "number" ? step.on_true_next_step : null;
    const falseT = typeof step.on_false_next_step === "number" ? step.on_false_next_step : null;
    if (trueT == null || falseT == null || trueT === falseT) continue;
    if (stepIndex === trueT) return { sibling: falseT, merge: Math.max(trueT, falseT) + 1 };
    if (stepIndex === falseT) return { sibling: trueT, merge: Math.max(trueT, falseT) + 1 };
  }
  return null;
}

function continueAfterStep(definitionSteps: Array<Record<string, unknown>>, stepIndex: number): number {
  const n = definitionSteps.length;
  if (stepIndex < 0 || stepIndex >= n) return n;
  const step = definitionSteps[stepIndex];
  if (typeof step.next_step === "number") return step.next_step as number;
  const candidate = stepIndex + 1;
  const siblingInfo = conditionSiblingArm(definitionSteps, stepIndex);
  if (siblingInfo && candidate === siblingInfo.sibling) return siblingInfo.merge;
  return candidate;
}

function computeReachableSteps(
  definitionSteps: Array<Record<string, unknown>>,
  context: Record<string, unknown>
): Set<number> {
  const reachable = new Set<number>();
  const n = definitionSteps.length;
  const groups = new Map<string, number[]>();
  definitionSteps.forEach((step, index) => {
    const g = typeof step.parallel_group === "string" && step.parallel_group ? step.parallel_group : "";
    if (!g) return;
    const bucket = groups.get(g) ?? [];
    bucket.push(index);
    groups.set(g, bucket);
  });

  let index = 0;
  let guard = 0;
  while (index >= 0 && index < n && guard < n + 2) {
    guard += 1;
    reachable.add(index);
    const step = definitionSteps[index];
    const stepType = typeof step.step_type === "string" ? step.step_type : "";
    if (step.parallel_group) {
      const members = groups.get(String(step.parallel_group))!;
      members.forEach((m) => reachable.add(m));
      index =
        typeof step.parallel_next_step === "number"
          ? (step.parallel_next_step as number)
          : Math.max(...members) + 1;
    } else if (stepType === "condition") {
      const result = evaluateCondition(step, context);
      const target = result
        ? typeof step.on_true_next_step === "number"
          ? (step.on_true_next_step as number)
          : index + 1
        : typeof step.on_false_next_step === "number"
        ? (step.on_false_next_step as number)
        : index + 1;
      index = target;
    } else {
      index = continueAfterStep(definitionSteps, index);
    }
  }
  return reachable;
}

function mapTaskStatus(status: string, instanceStatus: string): ApprovalStepStatus {
  const normalized = (status || "").toLowerCase();
  if (normalized === "approved") return "APPROVED";
  if (normalized === "rejected") return "REJECTED";
  if (instanceStatus === "completed") return "APPROVED";
  if (normalized === "pending" || normalized === "escalated") return "PENDING";
  // "cancelled" (e.g. sibling tasks cancelled after a rejection) has no
  // Ariba-native equivalent; showing it as waiting/greyed-out reads better
  // than approved or rejected.
  return "WAITING";
}

/**
 * Build the flat, ordered list of ApprovalStep cards for a WorkflowInstance,
 * given its definition's steps (for names/approver counts on not-yet-reached
 * steps) and a resolved map of user id -> display name. `definitionSteps`
 * comes straight off WorkflowDefinition.steps (Array<Record<string, unknown>>
 * -- a plain JSON column, see lib/types.ts), so fields are read defensively
 * the same way WorkflowCanvas.tsx does.
 */
export function buildApprovalSteps(
  instance: WorkflowInstance,
  definitionSteps: Array<Record<string, unknown>>,
  userNamesById: Record<string, string>
): ApprovalStep[] {
  const tasksByStepIndex = new Map<number, WorkflowTask[]>();
  for (const task of instance.tasks) {
    const list = tasksByStepIndex.get(task.step_index) ?? [];
    list.push(task);
    tasksByStepIndex.set(task.step_index, list);
  }

  const cards: ApprovalStep[] = [];
  const reachable = computeReachableSteps(definitionSteps, instance.context);

  definitionSteps.forEach((step, index) => {
    const stepType = typeof step.step_type === "string" ? step.step_type : "approval";
    if (stepType !== "approval") {
      // Condition/notification steps have no "approver" to show as a card;
      // the Ariba-style diagram is approval-focused.
      return;
    }
    // Off-path arms (e.g. No Approval when estimated_value took the Yes
    // branch) must not appear as Waiting sequential steps -- that was the
    // "3 approvals" bug for a 2-approver PR path.
    if (!reachable.has(index)) {
      return;
    }
    const stepName = typeof step.name === "string" ? step.name : "Approval";

    const tasks = tasksByStepIndex.get(index) ?? [];

    if (tasks.length === 0) {
      // Step hasn't produced any tasks yet -- either not reached yet, reached
      // but with zero approvers configured (a stuck step), or the instance is
      // blocked on this step. Show one placeholder card so the step stays
      // visible in sequence. Role-based steps (empty approvers list, role_code
      // set) are labelled by their role -- NOT "Unassigned".
      const approverCount = Array.isArray(step.approvers) ? step.approvers.length : 0;
      const roleCode = typeof step.role_code === "string" && step.role_code ? step.role_code : "";
      const isCurrent = index === instance.current_step_index;
      const approverName = approverCount > 0 ? "Pending assignment" : roleCode ? `${roleCode} (role)` : "Unassigned";
      const status =
        isCurrent && instance.status === "blocked"
          ? "BLOCKED"
          : isCurrent && instance.status === "in_progress"
          ? "PENDING"
          : "WAITING";
      cards.push({
        step_order: index,
        approver_name: approverName,
        approver_role: stepName,
        status,
        reason: typeof step.reason === "string" ? step.reason : undefined,
      });
      return;
    }

    tasks.forEach((task, taskIndex) => {
      cards.push({
        step_order: index + taskIndex * 0.01,
        approver_name: userNamesById[task.assignee_id] || "Unknown approver",
        approver_role: task.step_name || stepName,
        status: mapTaskStatus(task.status, instance.status),
        decided_at: task.completed_at || undefined,
        comment: task.comments || undefined,
        reason: task.reason || undefined,
        delegatedToName: task.escalate_to ? userNamesById[task.escalate_to] || "Unknown approver" : undefined,
        taskId: task.id,
      });
    });
  });

  return cards;
}

/** Resolve display names for every distinct assignee_id referenced by an
 * instance's tasks, via the non-admin-gated user directory (GET
 * /users/directory -- getUser()/listUsers() are admin-only and 403 for
 * regular users, which is exactly who needs to view an approval flow).
 * Best-effort: a lookup failure falls back to an empty map so a missing/
 * unreachable directory degrades to showing raw ids rather than failing the
 * whole diagram. */
export async function resolveApproverNames(instance: WorkflowInstance): Promise<Record<string, string>> {
  const ids = new Set(
    instance.tasks.flatMap((t) => [t.assignee_id, t.escalate_to]).filter((id): id is string => !!id)
  );
  if (ids.size === 0) {
    return {};
  }
  try {
    const { items } = await listUserDirectory({ limit: 1000 });
    const map: Record<string, string> = {};
    items.forEach((u) => {
      if (ids.has(u.id)) {
        map[u.id] = u.full_name || u.email || u.id;
      }
    });
    return map;
  } catch {
    return {};
  }
}
