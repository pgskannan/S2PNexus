import { listUserDirectory } from "@/lib/api";
import type { WorkflowInstance, WorkflowTask } from "@/lib/types";
import type { ApprovalStep, ApprovalStepStatus } from "@/components/ApprovalFlowDiagram";

// S2PNexus's generic workflow engine fans out one WorkflowTask per parallel
// approver on a step (see backend/app/crud/workflow.py::_run_from_step), and
// only creates tasks for a step once execution actually reaches it. The
// Ariba-style diagram wants one ApprovalStep card per approver in document
// order, including steps that haven't been reached yet (shown as "Waiting")
// -- this maps one onto the other.

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

  definitionSteps.forEach((step, index) => {
    const stepType = typeof step.step_type === "string" ? step.step_type : "approval";
    if (stepType !== "approval") {
      // Condition/notification steps have no "approver" to show as a card;
      // the Ariba-style diagram is approval-focused.
      return;
    }
    const stepName = typeof step.name === "string" ? step.name : "Approval";

    const tasks = tasksByStepIndex.get(index) ?? [];

    if (tasks.length === 0) {
      // Step hasn't produced any tasks yet -- either not reached yet, or
      // reached but has zero approvers configured (a stuck step). Either way,
      // show one placeholder card so the step is still visible in sequence.
      const approverCount = Array.isArray(step.approvers) ? step.approvers.length : 0;
      cards.push({
        step_order: index,
        approver_name: approverCount === 0 ? "Unassigned" : "Pending assignment",
        approver_role: stepName,
        status: index === instance.current_step_index && instance.status === "in_progress" ? "PENDING" : "WAITING",
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
  const ids = new Set(instance.tasks.map((t) => t.assignee_id).filter(Boolean));
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
