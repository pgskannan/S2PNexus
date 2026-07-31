"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  getPurchaseOrder,
  getRequisition,
  getWorkflowDefinition,
  listWorkflowInstances,
  getPurchaseOrderVersions,
  listPurchaseOrderComments,
  addPurchaseOrderComment,
  listUserDirectory,
  transitionPurchaseOrderLifecycle,
  acknowledgePurchaseOrder,
  getSupplier,
  extractErrorMessage,
} from "@/lib/api";
import type { PurchaseOrder, WorkflowInstance } from "@/lib/types";
import AccountingSplitEditor from "@/components/AccountingSplitEditor";
import DocumentTabs, { type DocumentSectionKey } from "@/components/DocumentTabs";
import CommentsPanel from "@/components/CommentsPanel";
import { ApprovalFlowDiagram, type ApprovalStep } from "@/components/ApprovalFlowDiagram";
import { buildApprovalSteps, resolveApproverNames } from "@/lib/approvalFlow";
import {
  fetchDocumentTabSignals,
  PR_APPROVED_LIFECYCLES,
  type DocumentTabSignals,
} from "@/lib/documentTabs";

const nextLifecycleSteps: Record<string, { value: string; label: string }[]> = {
  draft: [{ value: "pending_approval", label: "Submit for approval" }],
  pending_approval: [
    { value: "approved", label: "Approve" },
    { value: "cancelled", label: "Cancel" },
  ],
  approved: [
    { value: "ordered", label: "Mark ordered" },
    { value: "sent_to_supplier", label: "Send to supplier" },
    { value: "cancelled", label: "Cancel" },
  ],
  ordered: [
    { value: "sent_to_supplier", label: "Send to supplier" },
    { value: "cancelled", label: "Cancel" },
  ],
  sent_to_supplier: [{ value: "cancelled", label: "Cancel" }],
  acknowledged: [
    { value: "partially_received", label: "Mark partially received" },
    { value: "fully_received", label: "Mark fully received" },
    { value: "cancelled", label: "Cancel" },
  ],
  partially_received: [
    { value: "fully_received", label: "Mark fully received" },
    { value: "cancelled", label: "Cancel" },
  ],
  fully_received: [{ value: "invoiced", label: "Mark invoiced" }],
  invoiced: [{ value: "closed", label: "Close" }],
};

export default function PurchaseOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [supplierName, setSupplierName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastBudgetWarnings, setLastBudgetWarnings] = useState<PurchaseOrder["budget_warnings"]>(null);
  const [prId, setPrId] = useState<string | null>(null);
  const [prApproved, setPrApproved] = useState(false);
  const [docSignals, setDocSignals] = useState<DocumentTabSignals>({
    hasReceipts: false,
    hasInvoices: false,
    hasSubmittedInvoice: false,
    hasPayment: false,
  });
  const [activeSection, setActiveSection] = useState<DocumentSectionKey | null>(null);
  const [workflowInstance, setWorkflowInstance] = useState<WorkflowInstance | null>(null);
  const [approvalSteps, setApprovalSteps] = useState<ApprovalStep[]>([]);
  const [poVersions, setPoVersions] = useState<import("@/lib/types").PurchaseOrderVersion[]>([]);
  const [actorNames, setActorNames] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<import("@/lib/types").ProcurementComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [commentsError, setCommentsError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await getPurchaseOrder(params.id);
      setPo(data);
      if (data.supplier_id) {
        try {
          const supplier = await getSupplier(data.supplier_id);
          setSupplierName(supplier.name);
        } catch {
          setSupplierName(null);
        }
      }
      // Ariba-style tab visibility: derive the PR approval state plus
      // receipt/invoice existence from the real documents.
      setPrId(data.requisition_id ?? null);
      const [signals, requisition] = await Promise.all([
        fetchDocumentTabSignals(data.id),
        data.requisition_id ? getRequisition(data.requisition_id) : Promise.resolve(null),
      ]);
      setDocSignals(signals);
      setPrApproved(requisition ? PR_APPROVED_LIFECYCLES.has(requisition.lifecycle_status) : false);
      // Approval Flow / History / Comments panels for the PO: the PO's own
      // workflow instance, its version history, and its comment thread.
      const [wfRes, versions, directory] = await Promise.all([
        listWorkflowInstances({ entity_type: "purchase_order", entity_id: data.id }),
        getPurchaseOrderVersions(data.id),
        listUserDirectory({ limit: 1000 }).catch(() => null),
      ]);
      const instance = wfRes.items[0] ?? null;
      setWorkflowInstance(instance);
      setPoVersions(versions);
      setActorNames(
        directory
          ? Object.fromEntries(directory.items.map((user) => [user.id, user.full_name || user.email]))
          : {}
      );
      if (instance) {
        const [definition, approverNames] = await Promise.all([
          getWorkflowDefinition(instance.definition_id),
          resolveApproverNames(instance),
        ]);
        setApprovalSteps(buildApprovalSteps(instance, definition.steps, approverNames));
      } else {
        setApprovalSteps([]);
      }
      try {
        setComments(await listPurchaseOrderComments(data.id));
        setCommentsError(null);
      } catch (err2) {
        setCommentsError(extractErrorMessage(err2));
      } finally {
        setCommentsLoading(false);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleTransition(lifecycleStatus: string) {
    setBusy(true);
    setError(null);
    try {
      const updated = await transitionPurchaseOrderLifecycle(params.id, lifecycleStatus);
      setPo(updated);
      setLastBudgetWarnings(updated.budget_warnings ?? null);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAcknowledge() {
    setBusy(true);
    setError(null);
    try {
      const updated = await acknowledgePurchaseOrder(params.id);
      setPo(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAddComment(text: string) {
    const added = await addPurchaseOrderComment(params.id, text);
    setComments((current) => [added, ...current]);
  }

  if (error && !po) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!po) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  const actions = nextLifecycleSteps[po.lifecycle_status] ?? [];
  const canAcknowledge = po.lifecycle_status === "sent_to_supplier" && po.acknowledgment_status !== "acknowledged";

  return (
    <div className="max-w-4xl space-y-6">
      <DocumentTabs
        prId={prId}
        poId={po.id}
        prApproved={prApproved}
        signals={docSignals}
        activeSection={activeSection}
        onSectionChange={setActiveSection}
      />
      <button
        onClick={() => router.push("/dashboard/purchase-orders")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to purchase orders
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="font-mono text-xs text-slate-400">{po.order_number}</p>
            <h1 className="text-xl font-semibold">
              {supplierName ?? "Purchase order"}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Version {po.version_number}
              {po.amendment_status !== "original" ? ` · ${po.amendment_status}` : ""}
            </p>
          </div>
          <span className="badge bg-slate-100 text-slate-700 capitalize">
            {po.lifecycle_status}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Subtotal</dt>
            <dd>{po.currency} {po.subtotal ?? "0.00"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Shipping</dt>
            <dd>
              {po.currency} {po.shipping_amount ?? "0.00"}{" "}
              <span className="text-xs text-slate-400">({po.shipping_allocation_method})</span>
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Tax</dt>
            <dd>{po.currency} {po.tax_total ?? "0.00"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Grand total</dt>
            <dd className="font-semibold">{po.currency} {po.grand_total ?? po.total_amount ?? "0.00"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Incoterms</dt>
            <dd>{po.incoterms ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Payment terms</dt>
            <dd>{po.payment_terms ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Acknowledgment</dt>
            <dd className="capitalize">{po.acknowledgment_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Created</dt>
            <dd>{new Date(po.created_at).toLocaleString()}</dd>
          </div>
        </dl>

        <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 text-sm">
          <div>
            <dt className="text-slate-500">Ship to</dt>
            <dd>
              {po.ship_to_name ? (
                <>
                  {po.ship_to_name}
                  {po.ship_to_address_line1 ? `, ${po.ship_to_address_line1}` : ""}
                  {po.ship_to_city ? `, ${po.ship_to_city}` : ""}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Bill to</dt>
            <dd>
              {po.bill_to_name ? (
                <>
                  {po.bill_to_name}
                  {po.bill_to_address_line1 ? `, ${po.bill_to_address_line1}` : ""}
                  {po.bill_to_city ? `, ${po.bill_to_city}` : ""}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </div>

        {po.notes && (
          <p className="border-t border-slate-100 pt-4 text-sm text-slate-500">{po.notes}</p>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      {activeSection === "approval" && (
        <div className="space-y-2">
          {workflowInstance ? (
            <>
              <ApprovalFlowDiagram
                docNumber={po.order_number}
                title={supplierName ?? "Purchase order"}
                steps={approvalSteps}
              />
              <Link
                href={`/dashboard/workflow/instances/${workflowInstance.id}`}
                className="text-xs text-slate-400 hover:text-brand-600 hover:underline"
              >
                View raw workflow instance &rarr;
              </Link>
            </>
          ) : (
            <div className="card">
              <p className="text-sm text-slate-400">
                No approval workflow instance for this document.
              </p>
            </div>
          )}
        </div>
      )}

      {activeSection === "history" && (
        <div className="card">
          <h2 className="text-lg font-semibold">History · Versions</h2>
          {poVersions.length === 0 ? (
            <p className="mt-3 text-sm text-slate-400">No version history yet.</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100">
              {poVersions.map((v) => (
                <li key={v.id} className="py-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-slate-700">
                      V{v.version_number} ·{" "}
                      <span className="capitalize">{v.change_type.replace(/_/g, " ")}</span>
                    </span>
                    <time className="text-xs text-slate-400">{new Date(v.created_at).toLocaleString()}</time>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">By {actorNames[v.created_by] || "System"}</p>
                  {v.changes && Object.keys(v.changes).length > 0 && (
                    <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-600">
                      {JSON.stringify(v.changes, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {activeSection === "comments" && (
        <CommentsPanel
          items={comments}
          loading={commentsLoading}
          error={commentsError}
          authorNames={actorNames}
          onAdd={handleAddComment}
        />
      )}

      <div className="card space-y-3">
        <h2 className="text-lg font-semibold">Line items</h2>
        {po.line_items.length === 0 && (
          <p className="text-sm text-slate-400">No line items on this purchase order.</p>
        )}
        {po.line_items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Qty</th>
                  <th className="py-2 pr-4">Unit price</th>
                  <th className="py-2 pr-4">Line total</th>
                  <th className="py-2 pr-4">Shipping alloc.</th>
                  <th className="py-2 pr-4">Account code</th>
                  <th className="py-2 pr-4">Accounting split</th>
                </tr>
              </thead>
              <tbody>
                {po.line_items.map((li) => (
                  <tr key={li.id} className="border-b border-slate-50 last:border-0 align-top">
                    <td className="py-2 pr-4">{li.line_number}</td>
                    <td className="py-2 pr-4">{li.description}</td>
                    <td className="py-2 pr-4">{li.quantity}</td>
                    <td className="py-2 pr-4">{li.unit_price ?? "—"}</td>
                    <td className="py-2 pr-4">{li.line_total ?? "—"}</td>
                    <td className="py-2 pr-4">{li.allocated_shipping_amount ?? "—"}</td>
                    <td className="py-2 pr-4">
                      {li.account_code ?? "—"}
                      {li.account_code_is_override && (
                        <span className="ml-1 text-xs text-slate-400">(override)</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <AccountingSplitEditor
                        purchaseOrderId={po.id}
                        lineItemId={li.id}
                        lineTotal={li.line_total}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card space-y-4">
        <h2 className="text-lg font-semibold">Lifecycle</h2>

        {lastBudgetWarnings && lastBudgetWarnings.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            <p className="font-medium">Approved with budget warnings:</p>
            <ul className="mt-1 list-disc pl-5">
              {lastBudgetWarnings.map((w, i) => (
                <li key={i}>
                  {w.scope_level} {w.scope_code}: requested {w.requested_amount}, available {w.available}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          {canAcknowledge && (
            <button disabled={busy} onClick={handleAcknowledge} className="btn-secondary">
              Acknowledge receipt of PO
            </button>
          )}
          {actions.map((action) => (
            <button
              key={action.value}
              disabled={busy}
              onClick={() => handleTransition(action.value)}
              className="btn-primary"
            >
              {action.label}
            </button>
          ))}
        </div>
        {actions.length === 0 && !canAcknowledge && (
          <p className="text-sm text-slate-400">No further transitions available from this status.</p>
        )}
      </div>
    </div>
  );
}
