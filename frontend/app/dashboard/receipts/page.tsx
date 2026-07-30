"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { extractErrorMessage, listGoodsReceipts } from "@/lib/api";
import type { GoodsReceipt } from "@/lib/types";

const statusColors: Record<string, string> = {
  received: "bg-green-100 text-green-700",
  pending: "bg-amber-100 text-amber-700",
  hold: "bg-red-100 text-red-700",
};

export default function ReceiptsPage() {
  const [items, setItems] = useState<GoodsReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listGoodsReceipts()
      .then((result) => setItems(result.items))
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Receipts</h1>
        <p className="mt-1 text-sm text-slate-500">Track goods received against purchase orders.</p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <span className="rounded-full bg-slate-900 px-3 py-1.5 text-sm font-medium text-white">All <span className="ml-1 rounded-full bg-slate-700 px-1.5 text-xs">{items.length}</span></span>
        <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600">Exceptions <span className="ml-1 rounded-full bg-red-50 px-1.5 text-xs text-red-700">{items.filter((item) => item.has_exceptions).length}</span></span>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Receipt #</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Inspection</th><th className="px-4 py-3">Quantity</th><th className="px-4 py-3">Created</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {loading && <tr><td className="px-4 py-4 text-slate-400" colSpan={5}>Loading...</td></tr>}
            {!loading && items.length === 0 && <tr><td className="px-4 py-4 text-slate-400" colSpan={5}>No receipts yet.</td></tr>}
            {items.map((item) => <tr key={item.id} className="hover:bg-slate-50"><td className="px-4 py-3"><Link href={`/dashboard/purchase-orders/${item.purchase_order_id}`} className="font-medium text-brand-700 hover:underline">{item.receipt_number}</Link></td><td className="px-4 py-3"><span className={`badge ${statusColors[item.status] ?? "bg-slate-100 text-slate-700"}`}>{item.status}</span></td><td className="px-4 py-3 capitalize">{item.inspection_status}</td><td className="px-4 py-3">{item.received_quantity}</td><td className="px-4 py-3 text-slate-500">{new Date(item.created_at).toLocaleDateString()}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
