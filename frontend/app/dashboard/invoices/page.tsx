"use client";

import { useEffect, useState } from "react";
import { extractErrorMessage, listInvoices } from "@/lib/api";
import type { ProcurementInvoice } from "@/lib/types";

const statusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  matched: "bg-green-100 text-green-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

export default function InvoicesPage() {
  const [items, setItems] = useState<ProcurementInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listInvoices()
      .then((result) => setItems(result.items))
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  const exceptions = items.filter((item) => item.match_status !== "matched").length;

  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">Invoices</h1><p className="mt-1 text-sm text-slate-500">Monitor invoice status and three-way match progress.</p></div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2"><span className="rounded-full bg-slate-900 px-3 py-1.5 text-sm font-medium text-white">All <span className="ml-1 rounded-full bg-slate-700 px-1.5 text-xs">{items.length}</span></span><span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600">Needs review <span className="ml-1 rounded-full bg-amber-50 px-1.5 text-xs text-amber-700">{exceptions}</span></span></div>
      <div className="card overflow-x-auto p-0"><table className="min-w-full divide-y divide-slate-200 text-sm"><thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Invoice #</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Match</th><th className="px-4 py-3">Amount</th><th className="px-4 py-3">Created</th></tr></thead><tbody className="divide-y divide-slate-100">{loading && <tr><td className="px-4 py-4 text-slate-400" colSpan={5}>Loading...</td></tr>}{!loading && items.length === 0 && <tr><td className="px-4 py-4 text-slate-400" colSpan={5}>No invoices yet.</td></tr>}{items.map((item) => <tr key={item.id} className="hover:bg-slate-50"><td className="px-4 py-3 font-medium text-brand-700">{item.invoice_number}</td><td className="px-4 py-3"><span className={`badge ${statusColors[item.status] ?? "bg-slate-100 text-slate-700"}`}>{item.status}</span></td><td className="px-4 py-3 capitalize">{item.match_status.replace(/_/g, " ")}</td><td className="px-4 py-3">{item.currency} {item.total_amount ?? item.amount}</td><td className="px-4 py-3 text-slate-500">{new Date(item.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>
    </div>
  );
}
