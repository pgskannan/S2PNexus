"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getPurchaseOrder,
  transitionPurchaseOrderLifecycle,
  acknowledgePurchaseOrder,
  getSupplier,
  extractErrorMessage,
} from "@/lib/api";
import type { PurchaseOrder } from "@/lib/types";
import AccountingSplitEditor from "@/components/AccountingSplitEditor";

const nextLifecycleSteps: Record<string, { value: string; label: string }[]> = {
  draft: [{ value: "pending_approval", label: "Submit for approval" }],
  pending_approval: [
    { value: "approved", label: "Approve" },
    { value: "cancelled", label: "Cancel" },
  ],
  approved: [
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
