"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  getRequisition,
  listPurchaseOrders,
  listWorkflowInstances,
  transitionRequisition,
  extractErrorMessage,
} from "@/lib/api";
import type { PurchaseOrder, Requisition, WorkflowInstance } from "@/lib/types";

const nextSteps: Record<string, { new_status: string; lifecycle_status: string; label: string }[]> = {
  draft: [
    { new_status: "submitted", lifecycle_status: "submitted", label: "Submit for approval" },
  ],
  submitted: [
    { new_status: "approved", lifecycle_status: "approved", label: "Approve" },
    { new_status: "rejected", lifecycle_status: "rejected", label: "Reject" },
  ],
};

export default function RequisitionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [requisition, setRequisition] = useState<Requisition | null>(null);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [workflowInstance, setWorkflowInstance] = useState<WorkflowInstance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const data = await getRequisition(params.id);
      setRequisition(data);
      const poRes = await listPurchaseOrders({ requisition_id: params.id });
      setPurchaseOrders(poRes.items);
      // Surface the approval flow graph if a workflow instance exists for
      // this requisition -- WorkflowCanvas already renders it correctly at
      // /dashboard/workflow/instances/[id], it just had no entry point from
      // here.
      const wfRes = await listWorkflowInstances({
        entity_type: "requisition",
        entity_id: params.id,
      });
      setWorkflowInstance(wfRes.items[0] ?? null);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleTransition(newStatus: string, lifecycleStatus: string) {
    setBusy(true);
    setError(null);
    try {
      const updated = await transitionRequisition(
        params.id,
        newStatus,
        lifecycleStatus
      );
      setRequisition(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error && !requisition) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!requisition) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  const actions = nextSteps[requisition.lifecycle_status] ?? [];

  return (
    <div className="max-w-4xl space-y-6">
      <button
        onClick={() => router.push("/dashboard/requisitions")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to requisitions
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
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
            {workflowInstance && (
              <Link
                href={`/dashboard/workflow/instances/${workflowInstance.id}`}
                className="text-sm text-brand-600 hover:underline"
              >
                View approval flow &rarr;
              </Link>
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

      <div className="card space-y-4">
        {actions.length > 0 && (
          <div className="flex gap-3 border-t border-slate-100 pt-4">
            {actions.map((action) => (
              <button
                key={action.new_status}
                disabled={busy}
                onClick={() =>
                  handleTransition(action.new_status, action.lifecycle_status)
                }
                className="btn-primary"
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
        {actions.length === 0 && (
          <p className="border-t border-slate-100 pt-4 text-sm text-slate-400">
            No further transitions available from this status.
          </p>
        )}
      </div>
    </div>
  );
}
