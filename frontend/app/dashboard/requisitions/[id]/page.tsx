"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  adminRemoveWorkflowTask,
  completeWorkflowTask,
  deleteRequisition,
  getRequisition,
  getRequisitionApprovalPreview,
  getWorkflowDefinition,
  getWorkflowInstance,
  listMyWorkflowTasks,
  listPurchaseOrders,
  listWorkflowInstances,
  listRequisitionAuditEvents,
  listRequisitionComments,
  listRequisitionAttachments,
  addRequisitionAttachment,
  addRequisitionComment,
  listUserDirectory,
  retryWorkflowInstance,
  transitionRequisition,
  extractErrorMessage,
} from "@/lib/api";
import type {
  ProcurementAttachment,
  PurchaseOrder,
  Requisition,
  RequisitionApprovalPreview,
  WorkflowInstance,
  WorkflowTask,
} from "@/lib/types";
import { ApprovalFlowDiagram, type ApprovalStep } from "@/components/ApprovalFlowDiagram";
import { buildApprovalSteps, buildPreviewApprovalSteps, resolveApproverNames } from "@/lib/approvalFlow";
import DocumentTabs from "@/components/DocumentTabs";
import CommentsPanel from "@/components/CommentsPanel";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import {
  fetchDocumentTabSignals,
  type DocumentTabSignals,
} from "@/lib/documentTabs";
import { useAuthStore } from "@/lib/auth-store";

function sameId(a?: string | null, b?: string | null) {
  return Boolean(a && b && String(a).toLowerCase() === String(b).toLowerCase());
}

function canActAsApprover(user: { id: string; role: string; is_superuser: boolean } | null) {
  if (!user) return false;
  return user.is_superuser || user.role === "administrator";
}

const APPROVAL_PREVIEW_FIELD_LABELS: Record<string, string> = {
  estimated_value: "Estimated value",
  category: "Category",
  supplier_id: "Supplier",
  priority: "Priority",
  account_code: "GL/account code",
  commodity: "Commodity",
};

function approvalPreviewFieldLabel(field: string): string {
  return APPROVAL_PREVIEW_FIELD_LABELS[field] || field;
}

/** Pick the workflow task the current user should Approve/Reject on this PR. */
function resolveActionableTask(
  instance: WorkflowInstance | null,
  user: { id: string; role: string; is_superuser: boolean } | null,
  myTaskIds: Set<string>
): WorkflowTask | null {
  if (!instance || instance.status !== "in_progress" || !user) return null;
  const pending = instance.tasks.filter((task) => task.status === "pending" || task.status === "escalated");
  if (pending.length === 0) return null;

  const mine =
    pending.find((task) => sameId(task.assignee_id, user.id) || myTaskIds.has(String(task.id).toLowerCase())) ?? null;
  if (mine) return mine;

  // Admins can clear a stuck Active step from the PR page (backend already
  // allows complete_task for any authenticated actor; the old UI only linked
  // to My Tasks, which is empty when you aren't the assignee).
  if (!canActAsApprover(user)) return null;
  return (
    pending.find((task) => task.step_index === instance.current_step_index) ??
    pending[0] ??
    null
  );
}

const nextSteps: Record<string, { new_status: string; lifecycle_status: string; label: string }[]> = {
  draft: [
    { new_status: "submitted", lifecycle_status: "submitted", label: "Submit for approval" },
  ],
  submitted: [
    { new_status: "pending_approval", lifecycle_status: "pending_approval", label: "Send to approval" },
  ],
  pending_approval: [
    { new_status: "approved", lifecycle_status: "approved", label: "Approve" },
    { new_status: "rejected", lifecycle_status: "rejected", label: "Reject" },
  ],
  po_created: [
    { new_status: "closed", lifecycle_status: "closed", label: "Close PR" },
  ],
};

export default function RequisitionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const currentUser = useAuthStore((state) => state.user);
  const [requisition, setRequisition] = useState<Requisition | null>(null);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [workflowInstance, setWorkflowInstance] = useState<WorkflowInstance | null>(null);
  // Prevents the 1-second flash of lifecycle Approve/Reject before we know
  // whether a workflow task is owning the approval.
  const [workflowCheckDone, setWorkflowCheckDone] = useState(false);
  const [myTaskIds, setMyTaskIds] = useState<Set<string>>(new Set());
  const [approvalSteps, setApprovalSteps] = useState<ApprovalStep[]>([]);
  // Draft-stage dynamic approval preview (backlog follow-up 2026-08-04): only
  // fetched/shown while there's no real workflow instance yet, so the
  // requester can see how the PR would route -- and what's still missing --
  // before submitting.
  const [approvalPreview, setApprovalPreview] = useState<RequisitionApprovalPreview | null>(null);
  const [auditEvents, setAuditEvents] = useState<import("@/lib/types").ProcurementAuditEvent[]>([]);
  const [actorNames, setActorNames] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<import("@/lib/types").ProcurementComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  // Attachments (backlog Section 5): internal-only vs supplier-visible.
  const [attachments, setAttachments] = useState<ProcurementAttachment[]>([]);
  const [newAttachmentName, setNewAttachmentName] = useState("");
  const [newAttachmentInternal, setNewAttachmentInternal] = useState(false);
  const [attachmentBusy, setAttachmentBusy] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [docSignals, setDocSignals] = useState<DocumentTabSignals>({
    hasReceipts: false,
    hasInvoices: false,
    hasSubmittedInvoice: false,
    hasPayment: false,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondaryTab, setSecondaryTab] = useState<"approval" | "audit" | "comments">("approval");

  async function load() {
    setWorkflowCheckDone(false);
    try {
      const data = await getRequisition(params.id);
      setRequisition(data);
      const [poRes, auditRes, myTasks] = await Promise.all([
        listPurchaseOrders({ requisition_id: params.id }),
        listRequisitionAuditEvents(params.id),
        listMyWorkflowTasks({ status: "pending" }).catch(() => [] as WorkflowTask[]),
      ]);
      setPurchaseOrders(poRes.items);
      setAuditEvents(auditRes);
      setMyTaskIds(new Set(myTasks.map((task) => String(task.id).toLowerCase())));
      // Ariba-style tab visibility: receipts/invoices existence drives which
      // document tabs are shown once the PO exists.
      setDocSignals(await fetchDocumentTabSignals(poRes.items[0]?.id ?? null));
      try {
        setComments(await listRequisitionComments(params.id));
        setCommentsError(null);
      } catch (err2) {
        setCommentsError(extractErrorMessage(err2));
      } finally {
        setCommentsLoading(false);
      }
      listRequisitionAttachments(params.id)
        .then(setAttachments)
        .catch(() => setAttachments([]));
      const directory = await listUserDirectory({ limit: 1000 });
      setActorNames(Object.fromEntries(directory.items.map((user) => [user.id, user.full_name || user.email])));
      // Surface the approval flow inline (Ariba-style stepper) if a workflow
      // instance exists for this requisition. Prefer the detail endpoint so
      // tasks are always present (list payloads have occasionally been empty
      // in the UI race that hid Approve after 1s).
      const wfRes = await listWorkflowInstances({
        entity_type: "requisition",
        entity_id: params.id,
      });
      const listed = wfRes.items[0] ?? null;
      const instance = listed ? await getWorkflowInstance(listed.id).catch(() => listed) : null;
      setWorkflowInstance(instance);
      if (instance) {
        const [definition, approverNames] = await Promise.all([
          getWorkflowDefinition(instance.definition_id),
          resolveApproverNames(instance),
        ]);
        setApprovalSteps(buildApprovalSteps(instance, definition.steps, approverNames));
        setApprovalPreview(null);
      } else {
        setApprovalSteps([]);
        if (data.lifecycle_status === "draft") {
          getRequisitionApprovalPreview(params.id)
            .then(setApprovalPreview)
            .catch(() => setApprovalPreview(null));
        } else {
          setApprovalPreview(null);
        }
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setWorkflowCheckDone(true);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleAddComment(text: string) {
    const added = await addRequisitionComment(params.id, text);
    setComments((current) => [added, ...current]);
  }

  async function handleAddAttachment() {
    const name = newAttachmentName.trim();
    if (!name) {
      setAttachmentError("Filename is required.");
      return;
    }
    setAttachmentBusy(true);
    setAttachmentError(null);
    try {
      const added = await addRequisitionAttachment(params.id, {
        filename: name,
        is_internal_only: newAttachmentInternal,
      });
      setAttachments((current) => [added, ...current]);
      setNewAttachmentName("");
      setNewAttachmentInternal(false);
    } catch (err) {
      setAttachmentError(extractErrorMessage(err));
    } finally {
      setAttachmentBusy(false);
    }
  }

  async function handleTransition(newStatus: string, lifecycleStatus: string) {
    setBusy(true);
    setError(null);
    try {
      await transitionRequisition(params.id, newStatus, lifecycleStatus);
      // Re-run the full load(), not just setRequisition(updated) -- approving
      // can auto-create a PO and/or advance a workflow instance server-side
      // (see transition_requisition_endpoint), and this page's
      // purchaseOrders/workflowInstance/approvalSteps state was only ever
      // fetched once on initial mount. Without this, "Convert to PO" and the
      // approval diagram both silently show stale pre-transition state even
      // though the backend did the right thing.
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleWorkflowDecision(taskId: string, decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await completeWorkflowTask(taskId, { decision });
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAdminRemoveApproval(step: ApprovalStep) {
    if (!step.taskId) return;
    const confirmed = window.confirm(
      `Remove ${step.approver_name}'s approval step? The document will advance to its next status. This is logged as an admin override.`
    );
    if (!confirmed) return;
    const reason = window.prompt("Reason (optional):") ?? undefined;
    setBusy(true);
    setError(null);
    try {
      await adminRemoveWorkflowTask(step.taskId, reason || undefined);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleResumeWorkflow() {
    if (!workflowInstance) return;
    setBusy(true);
    setError(null);
    try {
      await retryWorkflowInstance(workflowInstance.id);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this draft requisition? This cannot be undone.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteRequisition(params.id);
      router.push("/dashboard/requisitions");
    } catch (err) {
      setError(extractErrorMessage(err));
      setBusy(false);
    }
  }

  async function handleWithdraw() {
    if (!confirm("Withdraw this submitted requisition? It will no longer be available for approval.")) {
      return;
    }
    await handleTransition("cancelled", "cancelled");
  }

  if (error && !requisition) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!requisition) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  // When a multi-step workflow is active, the lifecycle "Approve" shortcut is
  // blocked by the backend. Surface the assigned user's pending WorkflowTask
  // here (admins can also clear the Active step). Hold off showing lifecycle
  // Approve/Reject until the workflow check finishes so they don't flash for
  // ~1s and then vanish.
  const myPendingTask = resolveActionableTask(workflowInstance, currentUser, myTaskIds);
  const pendingWorkflowTaskCount =
    workflowInstance?.status === "in_progress"
      ? workflowInstance.tasks.filter((task) => task.status === "pending" || task.status === "escalated").length
      : 0;
  const approvedWorkflowTaskCount =
    workflowInstance?.tasks.filter((task) => task.status === "approved").length ?? 0;
  // Stuck after an approve that never advanced (autoflush bug): in progress,
  // some approvals done, nothing pending — admin can Resume to fan out the
  // next step (e.g. Yes Approval for Kannan).
  const workflowNeedsResume =
    Boolean(workflowInstance) &&
    workflowInstance?.status === "in_progress" &&
    pendingWorkflowTaskCount === 0 &&
    approvedWorkflowTaskCount > 0 &&
    requisition.lifecycle_status === "pending_approval";
  const canResumeWorkflow = canActAsApprover(currentUser) && (workflowNeedsResume || workflowInstance?.status === "blocked");
  const workflowBlocksDirectApprove =
    !workflowCheckDone ||
    pendingWorkflowTaskCount > 0 ||
    (requisition.lifecycle_status === "pending_approval" && Boolean(workflowInstance));
  const actions = (nextSteps[requisition.lifecycle_status] ?? []).filter((action) => {
    if (!workflowBlocksDirectApprove) return true;
    return action.lifecycle_status !== "approved" && action.lifecycle_status !== "rejected";
  });
  const actionBar = (
    <>
      {myPendingTask && (
        <>
          <button
            disabled={busy}
            onClick={() => handleWorkflowDecision(myPendingTask.id, "approve")}
            className="btn-primary"
          >
            Approve{canActAsApprover(currentUser) && !sameId(myPendingTask.assignee_id, currentUser?.id) ? " (admin)" : ""}
          </button>
          <button
            disabled={busy}
            onClick={() => handleWorkflowDecision(myPendingTask.id, "reject")}
            className="btn-secondary"
          >
            Reject
          </button>
        </>
      )}
      {canResumeWorkflow && (
        <button disabled={busy} onClick={() => handleResumeWorkflow()} className="btn-primary">
          Resume workflow
        </button>
      )}
      {actions.map((action) => (
        <button
          key={action.new_status}
          disabled={busy}
          onClick={() => handleTransition(action.new_status, action.lifecycle_status)}
          className="btn-primary"
        >
          {action.label}
        </button>
      ))}
      {requisition.lifecycle_status === "draft" && (
        <button
          disabled={busy}
          onClick={handleDelete}
          className="btn-secondary text-red-600 hover:bg-red-50"
        >
          Delete draft
        </button>
      )}
      {requisition.lifecycle_status === "submitted" && (
        <button
          disabled={busy}
          onClick={handleWithdraw}
          className="btn-secondary text-red-600 hover:bg-red-50"
        >
          Withdraw
        </button>
      )}
      <Link
        href={`/dashboard/requisitions/new?copy=${params.id}`}
        className="btn-secondary"
        title="Create a new requisition pre-filled from this one"
      >
        Copy PR
      </Link>
    </>
  );

  function auditLabel(action: string) {
    return action
      .split(":")
      .map((part) => part.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()))
      .join(" · ");
  }

  const prRecommendation = (() => {
    if (workflowInstance?.status === "blocked") {
      return "Approval is blocked: a step cannot resolve any approvers. Check the Approval Flow tab — an administrator must fix the approver setup (or retry the instance) before this can proceed.";
    }
    switch (requisition.lifecycle_status) {
      case "draft":
        return "This requisition is still a draft. Submit it for approval when it's ready.";
      case "submitted":
      case "pending_approval":
        return myPendingTask
          ? `Your approval is needed on "${myPendingTask.step_name}". Use Approve / Reject above.`
          : "Awaiting approval. Check the Approval Flow tab for who's Active, or open My Tasks if you are the assignee.";
      case "approved":
        return purchaseOrders.length === 0
          ? "Approved and ready — convert it to a PO to continue the P2P flow."
          : `Approved and converted. ${purchaseOrders.length} purchase order(s) linked.`;
      case "po_created":
        return `${purchaseOrders.length} purchase order(s) linked. Track progress on the PO tab.`;
      case "rejected":
        return "This requisition was rejected. Check the Approval Flow tab for details.";
      case "cancelled":
        return "This requisition was withdrawn/cancelled.";
      case "closed":
        return "Closed — no further action needed.";
      default:
        return "No action items right now.";
    }
  })();

  const prStripActions = [
    ...(requisition.lifecycle_status === "approved" && purchaseOrders.length === 0
      ? [{ label: "Convert to PO", tone: "critical" as const, href: `/dashboard/requisitions/${params.id}/convert-to-po` }]
      : []),
    ...(workflowInstance
      ? [
          {
            label: "Approval flow",
            tone: requisition.lifecycle_status === "pending_approval" ? ("warning" as const) : ("neutral" as const),
            onClick: () => setSecondaryTab("approval"),
          },
        ]
      : []),
    {
      label: `Audit log`,
      count: auditEvents.length,
      onClick: () => setSecondaryTab("audit"),
    },
    {
      label: `Comments`,
      count: comments.length,
      onClick: () => setSecondaryTab("comments"),
    },
  ];

  function auditSummary(event: import("@/lib/types").ProcurementAuditEvent) {
    const details = event.details || {};
    if (event.action === "purchase_order:created") return `Purchase order ${String(details.order_number || "created")}`;
    if (event.action === "workflow:started") return "Approval workflow started";
    if (event.action === "workflow:completed") return "All approval steps completed";
    if (event.action === "workflow:approved") return details.comments ? `Approved: ${String(details.comments)}` : "Approval granted";
    if (event.action === "workflow:rejected") return details.comments ? `Rejected: ${String(details.comments)}` : "Approval rejected";
    if (event.action.startsWith("transition:")) return `Requisition moved to ${event.action.split(":")[1].replace(/_/g, " ")}`;
    return "Activity recorded";
  }

  return (
    <div className="max-w-4xl space-y-6">
      <DocumentTabs
        prId={params.id}
        poId={purchaseOrders[0]?.id ?? null}
        signals={docSignals}
      />
      <button
        onClick={() => router.push("/dashboard/requisitions")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to requisitions
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            {requisition.requisition_number && (
              <p className="font-mono text-xs text-slate-400">{requisition.requisition_number}</p>
            )}
            <h1 className="text-xl font-semibold">{requisition.title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {requisition.description || "No description"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className="badge bg-slate-100 text-slate-700 capitalize">
              {requisition.lifecycle_status}
            </span>
            {(actions.length > 0 ||
              myPendingTask ||
              canResumeWorkflow ||
              requisition.lifecycle_status === "draft" ||
              requisition.lifecycle_status === "submitted") && (
              <div className="flex flex-wrap justify-end gap-2">{actionBar}</div>
            )}
            {canResumeWorkflow && (
              <p className="max-w-xs text-right text-xs text-amber-700">
                Workflow is stuck after a prior approval. Click Resume workflow to activate the next approver.
              </p>
            )}
            {requisition.lifecycle_status === "pending_approval" &&
              workflowCheckDone &&
              pendingWorkflowTaskCount > 0 &&
              !myPendingTask && (
              <p className="max-w-xs text-right text-xs text-slate-500">
                Waiting on {pendingWorkflowTaskCount} pending approval
                {pendingWorkflowTaskCount === 1 ? "" : "s"}. This step is assigned to someone else — open{" "}
                <Link href="/dashboard/workflow" className="text-brand-600 hover:underline">
                  My Tasks
                </Link>{" "}
                if you are the assignee, or check the Approval Flow tab for who is Active.
              </p>
            )}
            {myPendingTask && (
              <p className="max-w-xs text-right text-xs text-slate-500">
                {sameId(myPendingTask.assignee_id, currentUser?.id)
                  ? `Your turn: approve or reject "${myPendingTask.step_name}".`
                  : `Admin override: clear the active step "${myPendingTask.step_name}".`}
              </p>
            )}
            {requisition.lifecycle_status === "pending_approval" && !workflowCheckDone && (
              <p className="max-w-xs text-right text-xs text-slate-400">Checking approval workflow…</p>
            )}
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Priority</dt>
            <dd className="capitalize">{requisition.priority}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Estimated value</dt>
            <dd>
              {requisition.estimated_value
                ? `${requisition.currency} ${requisition.estimated_value}`
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Commodity</dt>
            <dd>{requisition.commodity || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Category</dt>
            <dd>{requisition.category || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Approval status</dt>
            <dd className="capitalize">{requisition.approval_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Created</dt>
            <dd>{new Date(requisition.created_at).toLocaleString()}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-slate-500">Ship to</dt>
            <dd>
              {requisition.ship_to_name || requisition.ship_to_address_line1 || requisition.ship_to_city ? (
                <span>
                  {[requisition.ship_to_name, requisition.ship_to_address_line1, requisition.ship_to_city]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      <ActionRecommendationStrip
        title="PR actions"
        description="Track this requisition's progress and jump to what needs attention."
        recommendation={prRecommendation}
        actions={prStripActions}
      />

      <div className="card space-y-3">
        <h2 className="text-lg font-semibold">Line items</h2>
        {(!requisition.line_items || requisition.line_items.length === 0) && (
          <p className="text-sm text-slate-400">No line items on this requisition.</p>
        )}
        {requisition.line_items && requisition.line_items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500">
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Qty</th>
                  <th className="py-2 pr-4">Unit price</th>
                  <th className="py-2 pr-4">Line total</th>
                  <th className="py-2 pr-4">Commodity</th>
                  <th className="py-2 pr-4">Category</th>
                  <th className="py-2 pr-4">Account code</th>
                </tr>
              </thead>
              <tbody>
                {requisition.line_items.map((li) => (
                  <tr key={li.id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2 pr-4">{li.description}</td>
                    <td className="py-2 pr-4">{li.quantity}</td>
                    <td className="py-2 pr-4">{li.unit_price ?? "—"}</td>
                    <td className="py-2 pr-4">{li.line_total ?? "—"}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{li.commodity ?? "—"}</td>
                    <td className="py-2 pr-4">{li.category ?? "—"}</td>
                    <td className="py-2 pr-4">{li.account_code ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Purchase orders</h2>
          {requisition.lifecycle_status === "approved" && purchaseOrders.length === 0 && (
            <button
              className="btn-primary"
              onClick={() =>
                router.push(`/dashboard/requisitions/${params.id}/convert-to-po`)
              }
            >
              Convert to PO
            </button>
          )}
        </div>
        {purchaseOrders.length === 0 && (
          <p className="text-sm text-slate-400">
            {requisition.lifecycle_status === "approved"
              ? "No purchase orders yet — use Convert to PO to create one."
              : "No purchase orders. A requisition must be approved before it can be converted."}
          </p>
        )}
        {purchaseOrders.length > 0 && (
          <ul className="divide-y divide-slate-100">
            {purchaseOrders.map((po) => (
              <li key={po.id} className="flex items-center justify-between py-2 text-sm">
                <div>
                  <Link
                    href={`/dashboard/purchase-orders/${po.id}`}
                    className="font-medium text-brand-600 hover:underline"
                  >
                    {po.order_number}
                  </Link>
                  <span className="ml-2 text-slate-400">
                    {po.currency} {po.grand_total ?? po.total_amount ?? "—"}
                  </span>
                </div>
                <span className="badge bg-slate-100 text-slate-700 capitalize">
                  {po.lifecycle_status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card space-y-4 p-0 overflow-hidden">
        <div className="flex gap-1 border-b border-slate-100 bg-slate-50 px-3 pt-2">
          {([
            { key: "approval", label: "Approval Flow" },
            { key: "audit", label: `Audit Log${auditEvents.length ? ` (${auditEvents.length})` : ""}` },
            { key: "comments", label: `Comments${comments.length ? ` (${comments.length})` : ""}` },
          ] as const).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSecondaryTab(tab.key)}
              className={`rounded-t-md px-3 py-2 text-sm font-medium transition ${
                secondaryTab === tab.key
                  ? "bg-white text-brand-700 border border-b-0 border-slate-100"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {secondaryTab === "approval" &&
            (workflowInstance ? (
              <div className="space-y-3">
                <ApprovalFlowDiagram
                  docNumber={requisition.requisition_number || undefined}
                  title={requisition.title}
                  steps={approvalSteps}
                  onAdminRemove={canActAsApprover(currentUser) ? handleAdminRemoveApproval : undefined}
                />
                {myPendingTask && (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                    <p className="text-sm text-amber-900">
                      You are the active approver for <span className="font-semibold">{myPendingTask.step_name}</span>.
                    </p>
                    <div className="flex gap-2">
                      <button
                        disabled={busy}
                        onClick={() => handleWorkflowDecision(myPendingTask.id, "approve")}
                        className="btn-primary"
                      >
                        Approve
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => handleWorkflowDecision(myPendingTask.id, "reject")}
                        className="btn-secondary"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                )}
                <Link
                  href={`/dashboard/workflow/instances/${workflowInstance.id}`}
                  className="text-xs text-slate-400 hover:text-brand-600 hover:underline"
                >
                  View raw workflow instance &rarr;
                </Link>
              </div>
            ) : requisition.lifecycle_status === "draft" && approvalPreview ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-medium uppercase text-slate-400">
                    Preview — based on current draft data, not yet submitted
                  </p>
                  {approvalPreview.definition_name && (
                    <p className="text-xs text-slate-400">{approvalPreview.definition_name}</p>
                  )}
                </div>
                {!approvalPreview.available ? (
                  <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    {approvalPreview.reason ||
                      "No active approval workflow is configured. An administrator needs to publish a requisition approval flow before this PR can be submitted."}
                  </p>
                ) : (
                  <>
                    {approvalPreview.steps.length > 0 && (
                      <ApprovalFlowDiagram
                        docNumber={requisition.requisition_number || undefined}
                        title={requisition.title}
                        steps={buildPreviewApprovalSteps(approvalPreview.steps)}
                      />
                    )}
                    {!approvalPreview.complete && (
                      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                        <p className="font-medium">Not enough information to determine the full approval flow.</p>
                        <p className="mt-1">
                          Still needed:{" "}
                          {approvalPreview.missing_fields.length > 0
                            ? approvalPreview.missing_fields.map(approvalPreviewFieldLabel).join(", ")
                            : "additional draft fields used by the workflow conditions"}
                          . Update the requisition and reopen this tab to refresh the preview.
                        </p>
                      </div>
                    )}
                    {approvalPreview.complete && approvalPreview.steps.length === 0 && (
                      <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                        Based on current data, this requisition would be auto-approved with no approval steps
                        (under the active workflow&apos;s routing thresholds).
                      </p>
                    )}
                    {approvalPreview.complete &&
                      approvalPreview.steps.some((step) => step.unresolved) && (
                        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                          One or more steps have no matching approver for this draft&apos;s category / amount /
                          supplier. Fix the Approver matrix or adjust the draft data before submitting.
                        </p>
                      )}
                  </>
                )}
              </div>
            ) : requisition.lifecycle_status === "draft" ? (
              <p className="text-sm text-slate-400">Loading approval flow preview…</p>
            ) : (
              <p className="text-sm text-slate-400">No approval workflow instance for this document.</p>
            ))}

          {secondaryTab === "audit" &&
            (auditEvents.length === 0 ? (
              <p className="text-sm text-slate-400">No audit events recorded yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {auditEvents.map((event) => (
                  <li key={event.id} className="py-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-slate-700">{auditLabel(event.action)}</span>
                      <time className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString()}</time>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">{auditSummary(event)}</p>
                    <p className="mt-1 text-xs text-slate-400">By {actorNames[event.actor_id] || "System user"}</p>
                  </li>
                ))}
              </ul>
            ))}

          {secondaryTab === "comments" && (
            <CommentsPanel
              items={comments}
              loading={commentsLoading}
              error={commentsError}
              authorNames={actorNames}
              onAdd={handleAddComment}
              bare
            />
          )}
        </div>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Attachments</h2>
          <span className="text-xs text-slate-400">
            Internal-only files are never shared with the supplier.
          </span>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label className="label" htmlFor="attachment-name">
              Filename
            </label>
            <input
              id="attachment-name"
              className="input-field"
              placeholder="e.g. vendor-quote.pdf"
              value={newAttachmentName}
              onChange={(e) => setNewAttachmentName(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={newAttachmentInternal}
              onChange={(e) => setNewAttachmentInternal(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            Internal only
          </label>
          <button
            onClick={handleAddAttachment}
            disabled={attachmentBusy}
            className="btn-primary"
          >
            {attachmentBusy ? "Adding…" : "Add attachment"}
          </button>
        </div>
        {attachmentError && <p className="text-sm text-red-600">{attachmentError}</p>}

        {attachments.length === 0 ? (
          <p className="text-sm text-slate-400">No attachments yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {attachments.map((att) => (
              <li key={att.id} className="flex items-center justify-between py-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-700">{att.filename}</span>
                  {att.is_internal_only ? (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                      Internal only
                    </span>
                  ) : (
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                      Supplier-visible
                    </span>
                  )}
                </div>
                <time className="text-xs text-slate-400">{new Date(att.created_at).toLocaleString()}</time>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
