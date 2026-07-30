"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listRequisitions, extractErrorMessage, listSuppliers } from "@/lib/api";
import CategoryInput from "@/components/CategoryInput";
import type { Requisition } from "@/lib/types";

const statusColors: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  submitted: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

export default function RequisitionsPage() {
  const [items, setItems] = useState<Requisition[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [category, setCategory] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suppliers, setSuppliers] = useState([] as any[]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params: any = { search: search || undefined };
      if (status) params.status = status;
      if (category) params.category = category;
      if (supplierId) params.supplier_id = supplierId;
      if (createdAfter) params.created_after = createdAfter;
      if (createdBefore) params.created_before = createdBefore;
      const res = await listRequisitions(params);
      setItems(res.items);
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

  useEffect(() => {
    listSuppliers()
      .then((r) => setSuppliers(r.items))
      .catch(() => setSuppliers([]));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Requisitions</h1>
        <Link href="/dashboard/requisitions/new" className="btn-primary">
          + New Requisition
        </Link>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        className="flex gap-2 flex-wrap items-end"
      >
        <input
          className="input-field max-w-xs"
          placeholder="Search title..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="input-field" value={status || ""} onChange={(e) => setStatus(e.target.value || undefined)}>
          <option value="">Any status</option>
          <option value="draft">Draft</option>
          <option value="submitted">Submitted</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <div style={{ minWidth: 220 }}>
          <CategoryInput value={category} onChange={setCategory} />
        </div>
        <select className="input-field" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
          <option value="">Any supplier</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <label className="text-xs text-slate-500">Created after</label>
        <input type="date" className="input-field" value={createdAfter} onChange={(e) => setCreatedAfter(e.target.value)} />
        <label className="text-xs text-slate-500">Created before</label>
        <input type="date" className="input-field" value={createdBefore} onChange={(e) => setCreatedBefore(e.target.value)} />
        <button type="submit" className="btn-secondary">
          Apply
        </button>
        <button type="button" className="btn-secondary" onClick={async () => {
          // Re-fetch up to 1000 for export
          const params: any = { search: search || undefined, limit: 1000 };
          if (status) params.status = status;
          if (category) params.category = category;
          if (supplierId) params.supplier_id = supplierId;
          if (createdAfter) params.created_after = createdAfter;
          if (createdBefore) params.created_before = createdBefore;
          try {
            const res = await listRequisitions(params);
            const rows = res.items;
            const cols = ["requisition_number","title","status","priority","estimated_value","currency","created_at"];
            const csv = [cols.join(",")].concat(rows.map(r => cols.map(c => {
              const v = (r as any)[c];
              if (v === undefined || v === null) return "";
              return String(v).replace(/"/g,'""');
            }).map(v=>`"${v}"`).join(",")) ).join("\n");
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'requisitions_export.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
          } catch (err) {
            alert('Export failed: ' + (err as any).message || 'unknown');
          }
        }}>
          Export CSV
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Number</th>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Est. value</th>
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
                  No requisitions yet.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  {item.requisition_number || "—"}
                </td>
                <td className="px-4 py-3">
                  <Link
                    href={`/dashboard/requisitions/${item.id}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {item.title}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`badge ${
                      statusColors[item.lifecycle_status] ??
                      "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {item.lifecycle_status}
                  </span>
                </td>
                <td className="px-4 py-3 capitalize">{item.priority}</td>
                <td className="px-4 py-3">
                  {item.estimated_value
                    ? `${item.currency} ${item.estimated_value}`
                    : "—"}
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(item.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
