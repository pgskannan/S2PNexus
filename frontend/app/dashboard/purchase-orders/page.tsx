"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listPurchaseOrders, listSuppliers, extractErrorMessage } from "@/lib/api";
import type { PurchaseOrder } from "@/lib/types";

const statusColors: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  pending_approval: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  sent_to_supplier: "bg-blue-100 text-blue-700",
  acknowledged: "bg-blue-100 text-blue-700",
  partially_received: "bg-purple-100 text-purple-700",
  fully_received: "bg-green-100 text-green-700",
  closed: "bg-slate-100 text-slate-700",
  cancelled: "bg-red-100 text-red-700",
};

export default function PurchaseOrdersPage() {
  const [items, setItems] = useState<PurchaseOrder[]>([]);
  const [supplierNames, setSupplierNames] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [res, supplierRes] = await Promise.all([
        listPurchaseOrders({ status: statusFilter || undefined }),
        listSuppliers(),
      ]);
      setItems(res.items);
      setSupplierNames(
        Object.fromEntries(supplierRes.items.map((s) => [s.id, s.name]))
      );
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Purchase Orders</h1>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        className="flex gap-2"
      >
        <select
          className="input-field max-w-xs"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="pending_approval">Pending approval</option>
          <option value="approved">Approved</option>
          <option value="sent_to_supplier">Sent to supplier</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="partially_received">Partially received</option>
          <option value="fully_received">Fully received</option>
          <option value="closed">Closed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <button type="submit" className="btn-secondary">
          Filter
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Order #</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Supplier</th>
              <th className="px-4 py-3">Ship to</th>
              <th className="px-4 py-3">Total</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  No purchase orders yet. Convert an approved requisition to create one.
                </td>
              </tr>
            )}
            {items.map((po) => (
              <tr key={po.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/dashboard/purchase-orders/${po.id}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {po.order_number}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`badge ${
                      statusColors[po.lifecycle_status] ?? "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {po.lifecycle_status}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {po.supplier_id ? supplierNames[po.supplier_id] ?? "—" : "—"}
                </td>
                <td className="px-4 py-3">{po.ship_to_name ?? "—"}</td>
                <td className="px-4 py-3">
                  {po.currency} {po.grand_total ?? po.total_amount ?? "—"}
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(po.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
