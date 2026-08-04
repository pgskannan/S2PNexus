"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { extractErrorMessage, getGoodsReceipt, getPurchaseOrder } from "@/lib/api";
import DocumentTabs from "@/components/DocumentTabs";
import type { GoodsReceipt, PurchaseOrder } from "@/lib/types";

const statusColors: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  submitted: "bg-amber-100 text-amber-700",
  in_review: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700",
  posted: "bg-green-100 text-green-700",
  received: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  cancelled: "bg-slate-200 text-slate-500",
};

function fmt(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function ReceiptDetailPage() {
  const params = useParams<{ id: string }>();
  const [receipt, setReceipt] = useState<GoodsReceipt | null>(null);
  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await getGoodsReceipt(params.id);
        if (cancelled) return;
        setReceipt(r);
        try {
          const p = await getPurchaseOrder(r.purchase_order_id);
          if (!cancelled) setPo(p);
        } catch {
          // PO lookup is only used for context (breadcrumb, line descriptions) --
          // the receipt itself still renders if it fails.
        }
      } catch (err) {
        if (!cancelled) setError(extractErrorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const lineDescription = (poLineItemId: string) =>
    po?.line_items.find((li) => li.id === poLineItemId)?.description ?? "—";

  if (loading) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  if (error || !receipt) {
    return <p className="text-sm text-red-600">{error ?? "Receipt not found."}</p>;
  }

  return (
    <div className="space-y-6">
      <DocumentTabs prId={po?.requisition_id ?? null} poId={receipt.purchase_order_id} />

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Receipt {receipt.receipt_number}</h1>
          <p className="mt-1 text-sm text-slate-500">
            Against purchase order{" "}
            <span className="font-mono">{po?.order_number ?? receipt.purchase_order_id}</span>
          </p>
        </div>
        <Link href={`/dashboard/purchase-orders/${receipt.purchase_order_id}`} className="btn-secondary">
          ← Back to PO
        </Link>
      </div>

      <div className="card grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase text-slate-400">Status</dt>
          <dd className="mt-1">
            <span className={`badge ${statusColors[receipt.status] ?? "bg-slate-100 text-slate-700"}`}>
              {receipt.status.replace(/_/g, " ")}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-400">Inspection</dt>
          <dd className="mt-1 capitalize text-sm text-slate-700">{receipt.inspection_status}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-400">Received qty</dt>
          <dd className="mt-1 text-sm text-slate-700">{receipt.received_quantity}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-400">Returned/rejected qty</dt>
          <dd className="mt-1 text-sm text-slate-700">{receipt.returned_quantity}</dd>
        </div>
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-slate-700">Shipment</h2>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase text-slate-400">Shipment notice / delivery note</dt>
            <dd className="mt-1 text-sm text-slate-700">{receipt.delivery_note_reference || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-400">Carrier</dt>
            <dd className="mt-1 text-sm text-slate-700">{receipt.carrier || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-400">Tracking number</dt>
            <dd className="mt-1 text-sm text-slate-700">{receipt.tracking_number || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-400">Delivery date</dt>
            <dd className="mt-1 text-sm text-slate-700">{fmt(receipt.posted_at || receipt.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-400">Receipt type</dt>
            <dd className="mt-1 text-sm capitalize text-slate-700">{receipt.receipt_type}</dd>
          </div>
        </dl>
      </div>

      {(receipt.submitted_at || receipt.approved_at || receipt.posted_at || receipt.rejected_at) && (
        <div className="card">
          <h2 className="text-sm font-semibold text-slate-700">Approval timeline</h2>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
            {receipt.submitted_at && <span>Submitted {fmt(receipt.submitted_at)}</span>}
            {receipt.approved_at && <span>Approved {fmt(receipt.approved_at)}</span>}
            {receipt.posted_at && <span>Posted {fmt(receipt.posted_at)}</span>}
            {receipt.rejected_at && <span>Rejected {fmt(receipt.rejected_at)}</span>}
          </div>
          {receipt.rejection_reason && (
            <p className="mt-2 text-xs text-red-600">Reason: {receipt.rejection_reason}</p>
          )}
        </div>
      )}

      {receipt.notes && (
        <div className="card">
          <h2 className="text-sm font-semibold text-slate-700">Comments</h2>
          <p className="mt-2 text-sm text-slate-600">{receipt.notes}</p>
        </div>
      )}

      <div className="card overflow-x-auto p-0">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">Line items</h2>
        </div>
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Received</th>
              <th className="px-4 py-3">Rejected</th>
              <th className="px-4 py-3">Accepted</th>
              <th className="px-4 py-3">Condition</th>
              <th className="px-4 py-3">Lot #</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {receipt.line_items.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  No line items on this receipt.
                </td>
              </tr>
            )}
            {receipt.line_items.map((li) => (
              <tr key={li.id}>
                <td className="px-4 py-3">{lineDescription(li.purchase_order_line_item_id)}</td>
                <td className="px-4 py-3">{li.quantity_received}</td>
                <td className="px-4 py-3">{li.quantity_rejected}</td>
                <td className="px-4 py-3">{li.quantity_accepted}</td>
                <td className="px-4 py-3 capitalize">{li.condition_status}</td>
                <td className="px-4 py-3">{li.lot_number || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
