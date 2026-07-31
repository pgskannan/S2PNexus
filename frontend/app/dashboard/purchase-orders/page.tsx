"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listPurchaseOrders, listSuppliers, extractErrorMessage } from "@/lib/api";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import type { PurchaseOrder, Supplier } from "@/lib/types";

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
  invoiced: "bg-indigo-100 text-indigo-700",
};

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "pending_approval", label: "Pending approval" },
  { value: "approved", label: "Approved" },
  { value: "sent_to_supplier", label: "Sent to supplier" },
  { value: "acknowledged", label: "Acknowledged" },
  { value: "partially_received", label: "Partially received" },
  { value: "fully_received", label: "Fully received" },
  { value: "invoiced", label: "Invoiced" },
  { value: "closed", label: "Closed" },
  { value: "cancelled", label: "Cancelled" },
];

const HIGH_VALUE_THRESHOLD = 10000;
const OPEN_FOR_RECEIVING = new Set(["approved", "sent_to_supplier", "acknowledged", "partially_received"]);

export default function PurchaseOrdersPage() {
  const [items, setItems] = useState<PurchaseOrder[]>([]);
  const [allItems, setAllItems] = useState<PurchaseOrder[]>([]);
  const [supplierNames, setSupplierNames] = useState<Record<string, string>>({});
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [supplierFilter, setSupplierFilter] = useState("");
  const [highValueOnly, setHighValueOnly] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [res, allRes, supplierRes] = await Promise.all([
        listPurchaseOrders({ status: statusFilter || undefined, limit: 200 }),
        listPurchaseOrders({ limit: 500 }),
        listSuppliers(),
      ]);
      setItems(res.items);
      setAllItems(allRes.items);
      setSupplierNames(Object.fromEntries(supplierRes.items.map((s) => [s.id, s.name])));
      setSuppliers(supplierRes.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  function orderValue(po: PurchaseOrder): number {
    const raw = po.grand_total ?? po.total_amount;
    return raw ? Number(raw) : 0;
  }

  const displayedItems = useMemo(() => {
    return items.filter((po) => {
      if (search && !po.order_number.toLowerCase().includes(search.toLowerCase())) return false;
      if (supplierFilter && po.supplier_id !== supplierFilter) return false;
      if (highValueOnly && orderValue(po) <= HIGH_VALUE_THRESHOLD) return false;
      return true;
    });
  }, [items, search, supplierFilter, highValueOnly]);

  const needsApprovalCount = allItems.filter((po) => po.lifecycle_status === "pending_approval").length;
  const openForReceivingCount = allItems.filter((po) => OPEN_FOR_RECEIVING.has(po.lifecycle_status)).length;
  const highValueCount = allItems.filter((po) => orderValue(po) > HIGH_VALUE_THRESHOLD).length;

  const recommendation =
    needsApprovalCount > 0
      ? `${needsApprovalCount} purchase order(s) are pending approval. Prioritize high-value or older orders to avoid delaying suppliers.`
      : openForReceivingCount > 0
      ? `${openForReceivingCount} purchase order(s) are open for receiving. Confirm receipt as goods arrive to keep the invoice match clean.`
      : "Approval queue is clear. No purchase orders need attention right now.";

  const activeFilterCount = [supplierFilter, highValueOnly ? "y" : ""].filter((v) => v).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Purchase Orders</h1>
      </div>

      <ActionRecommendationStrip
        title="Purchase order actions"
        description="Jump into pending approvals, track receiving status, or monitor high-value spend."
        recommendation={recommendation}
        actions={[
          {
            label: "Needs approval",
            count: needsApprovalCount,
            tone: "critical",
            onClick: () => setStatusFilter("pending_approval"),
          },
          {
            label: "Open for receiving",
            count: openForReceivingCount,
            tone: "neutral",
            onClick: () => setStatusFilter("partially_received"),
          },
          {
            label: `High value (>$${HIGH_VALUE_THRESHOLD.toLocaleString()})`,
            count: highValueCount,
            tone: "warning",
            onClick: () => {
              setStatusFilter("");
              setHighValueOnly(true);
            },
          },
        ]}
      />

      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs text-slate-500">Search</label>
            <input
              className="input-field"
              placeholder="Order number..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-2"
            onClick={() => setFiltersOpen((v) => !v)}
          >
            Filters
            {activeFilterCount > 0 && (
              <span className="rounded-full bg-slate-900 px-1.5 text-xs text-white">{activeFilterCount}</span>
            )}
            <span className="text-xs">{filtersOpen ? "▲" : "▼"}</span>
          </button>
        </div>

        {filtersOpen && (
          <div className="flex flex-wrap gap-2 items-end border-t border-slate-100 pt-3">
            <div>
              <label className="text-xs text-slate-500">Status</label>
              <select className="input-field" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                {STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Supplier</label>
              <select className="input-field" value={supplierFilter} onChange={(e) => setSupplierFilter(e.target.value)}>
                <option value="">Any supplier</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600 pb-2">
              <input type="checkbox" checked={highValueOnly} onChange={(e) => setHighValueOnly(e.target.checked)} />
              High value only
            </label>
            {activeFilterCount > 0 && (
              <button
                type="button"
                className="text-xs text-red-600 hover:underline pb-2"
                onClick={() => {
                  setSupplierFilter("");
                  setHighValueOnly(false);
                }}
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </div>

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
            {!loading && displayedItems.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  No purchase orders match these filters.
                </td>
              </tr>
            )}
            {displayedItems.map((po) => (
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
