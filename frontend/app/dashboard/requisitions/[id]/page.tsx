"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  deleteRequisition,
  getRequisition,
  getWorkflowDefinition,
  listPurchaseOrders,
  listGoodsReceipts,
  listInvoices,
  listWorkflowInstances,
  listRequisitionAuditEvents,
  listRequisitionComments,
  addRequisitionComment,
  listUserDirectory,
  transitionRequisition,
  extractErrorMessage,
} from "@/lib/api";
import type { PurchaseOrder, Requisition, WorkflowInstance } from "@/lib/types";
import { ApprovalFlowDiagram, type ApprovalStep } from "@/components/ApprovalFlowDiagram";
import { buildApprovalSteps, resolveApproverNames } from "@/lib/approvalFlow";
import DocumentTabs from "@/components/DocumentTabs";
import CommentsPanel from "@/components/CommentsPanel";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import {
  fetchDocumentTabSignals,
  type DocumentTabSignals,
} from "@/lib/documentTabs";

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
  const [requisition, setRequisition] = useState<Requisition | null>(null);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [workflowInstance, setWorkflowInstance] = useState<WorkflowInstance | null>(null);
  const [approvalSteps, setApprovalSteps] = useState<ApprovalStep[]>([]);
  const [auditEvents, setAuditEvents] = useState<import("@/lib/types").ProcurementAuditEvent[]>([]);
  const [actorNames, setActorNames] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<import("@/lib/types").ProcurementComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [commentsError, setCommentsError] = useState<string | null>(null);
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
    try {
      const data = await getRequisition(params.id);
      setRequisition(data);
      const [poRes, auditRes] = await Promise.all([
        listPurchaseOrders({ requisition_id: params.id }),
        listRequisitionAuditEvents(params.id),
      ]);
      setPurchaseOrders(poRes.items);
      setAuditEvents(auditRes);
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
      const directory = await listUserDirectory({ limit: 1000 });
      setActorNames(Object.fromEntries(directory.items.map((user) => [user.id, user.full_name || user.email])));
      // Surface the approval flow inline (Ariba-style stepper) if a workflow
      // instance exists for this requisition.
      const wfRes = await listWorkflowInstances({
        entity_type: "requisition",
        entity_id: params.id,
      });
      const instance = wfRes.items[0] ?? null;
      setWorkflowInstance(instance);
      if (instance) {
        const [definition, approverNames] = await Promise.all([
          getWorkflowDefinition(instance.definition_id),
          resolveApproverNames(instance),
        ]);
        setApprovalSteps(buildApprovalSteps(instance, definition.steps, approverNames));
      } else {
        setApprovalSteps([]);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
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

  // Mirrors the backend guard in transition_requisition_endpoint: hide the
  // one-click "Approve" shortcut whenever a real multi-step workflow is
  // actively waiting on other approvers, so the only path to approve is the
  // assigned approver's own task. Still shown for requisitions with no
  // workflow instance at all (workflowInstance stays null in that case).
  const pendingWorkflowTaskCount =
    workflowInstance?.status === "in_progress"
      ? workflowInstance.tasks.filter((task) => task.status === "pending" || task.status === "escalated").length
      : 0;
  const actions = (nextSteps[requisition.lifecycle_status] ?? []).filter(
    (action) => !(action.lifecycle_status === "approved" && pendingWorkflowTaskCount > 0)
  );
  const actionBar = (
    <>
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
        return "Awaiting approval. Check the Approval Flow tab for who's up next.";
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
            {(actions.length > 0 || requisition.lifecycle_status === "draft" || requisition.lifecycle_status === "submitted") && (
              <div className="flex flex-wrap justify-end gap-2">{actionBar}</div>
            )}
            {requisition.lifecycle_status === "pending_approval" && pendingWorkflowTaskCount > 0 && (
              <p className="max-w-xs text-right text-xs text-slate-500">
                Waiting on {pendingWorkflowTaskCount} pending approval{pendingWorkflowTaskCount === 1 ? "" : "s"} in the
                Approval Flow tab below -- approve from there, not here.
              </p>
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
              <div className="space-y-2">
                <ApprovalFlowDiagram
                  docNumber={requisition.requisition_number || undefined}
                  title={requisition.title}
                  steps={approvalSteps}
                />
                <Link
                  href={`/dashboard/workflow/instances/${workflowInstance.id}`}
                  className="text-xs text-slate-400 hover:text-brand-600 hover:underline"
                >
                  View raw workflow instance &rarr;
                </Link>
              </div>
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
    </div>
  );
}
