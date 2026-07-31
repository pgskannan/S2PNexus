"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { extractErrorMessage, listGoodsReceipts } from "@/lib/api";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import type { GoodsReceipt } from "@/lib/types";

const statusColors: Record<string, string> = {
  received: "bg-green-100 text-green-700",
  pending: "bg-amber-100 text-amber-700",
  hold: "bg-red-100 text-red-700",
};

type QuickFilter = "" | "exceptions" | "pending_inspection";

export default function ReceiptsPage() {
  const [items, setItems] = useState<GoodsReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [poFilter, setPoFilter] = useState<string | null>(null);

  useEffect(() => {
    listGoodsReceipts()
      .then((result) => setItems(result.items))
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setPoFilter(params.get("po"));
  }, []);

  const exceptionsCount = items.filter((item) => item.has_exceptions).length;
  const pendingInspectionCount = items.filter((item) => item.inspection_status === "pending").length;

  const recommendation =
    exceptionsCount > 0
      ? `${exceptionsCount} receipt(s) have exceptions. Resolve these before they block invoice matching.`
      : pendingInspectionCount > 0
      ? `${pendingInspectionCount} receipt(s) are awaiting inspection. Clear the queue to keep receiving current.`
      : "No exceptions or pending inspections. Receiving is on track.";

  const displayedItems = useMemo(() => {
    return items.filter((item) => {
      if (poFilter && item.purchase_order_id !== poFilter) return false;
      if (search && !item.receipt_number.toLowerCase().includes(search.toLowerCase())) return false;
      if (statusFilter && item.status !== statusFilter) return false;
      if (quickFilter === "exceptions" && !item.has_exceptions) return false;
      if (quickFilter === "pending_inspection" && item.inspection_status !== "pending") return false;
      return true;
    });
  }, [items, search, statusFilter, quickFilter, poFilter]);

  const activeFilterCount = [statusFilter, quickFilter].filter((v) => v).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Receipts</h1>
        <p className="mt-1 text-sm text-slate-500">Track goods received against purchase orders.</p>
      </div>
      {poFilter && (
        <div className="flex items-center justify-between rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-700">
          <span>
            Showing receipts for purchase order <span className="font-mono">{poFilter}</span>
          </span>
          <button type="button" onClick={() => setPoFilter(null)} className="text-xs font-medium underline">
            Clear filter
          </button>
        </div>
      )}

      <ActionRecommendationStrip
        title="Receipt actions"
        description="Resolve exceptions and clear pending inspections to keep receiving on track."
        recommendation={recommendation}
        actions={[
          {
            label: "Exceptions",
            count: exceptionsCount,
            tone: "critical",
            onClick: () => setQuickFilter(quickFilter === "exceptions" ? "" : "exceptions"),
          },
          {
            label: "Pending inspection",
            count: pendingInspectionCount,
            tone: "warning",
            onClick: () => setQuickFilter(quickFilter === "pending_inspection" ? "" : "pending_inspection"),
          },
        ]}
      />

      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs text-slate-500">Search</label>
            <input
              className="input-field"
              placeholder="Receipt number..."
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
                <option value="">All statuses</option>
                <option value="received">Received</option>
                <option value="pending">Pending</option>
                <option value="hold">Hold</option>
              </select>
            </div>
            {activeFilterCount > 0 && (
              <button
                type="button"
                className="text-xs text-red-600 hover:underline pb-2"
                onClick={() => {
                  setStatusFilter("");
                  setQuickFilter("");
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
              <th className="px-4 py-3">Receipt #</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Inspection</th>
              <th className="px-4 py-3">Quantity</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={5}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && displayedItems.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={5}>
                  No receipts match these filters.
                </td>
              </tr>
            )}
            {displayedItems.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/dashboard/purchase-orders/${item.purchase_order_id}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {item.receipt_number}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span className={`badge ${statusColors[item.status] ?? "bg-slate-100 text-slate-700"}`}>
                    {item.status}
                  </span>
                </td>
                <td className="px-4 py-3 capitalize">{item.inspection_status}</td>
                <td className="px-4 py-3">{item.received_quantity}</td>
                <td className="px-4 py-3 text-slate-500">{new Date(item.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
