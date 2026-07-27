"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listSuppliers, extractErrorMessage } from "@/lib/api";
import type { Supplier } from "@/lib/types";

export default function SuppliersPage() {
  const [items, setItems] = useState<Supplier[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listSuppliers({ search: search || undefined });
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Suppliers</h1>
        <Link href="/dashboard/suppliers/new" className="btn-primary">
          + New Supplier
        </Link>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        className="flex gap-2"
      >
        <input
          className="input-field max-w-xs"
          placeholder="Search name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="btn-secondary">
          Search
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Contact</th>
              <th className="px-4 py-3">Payment terms</th>
              <th className="px-4 py-3">Lifecycle status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={4}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={4}>
                  No suppliers yet.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-medium">
                  <Link
                    href={`/dashboard/suppliers/${item.id}`}
                    className="text-brand-700 hover:underline"
                  >
                    {item.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {item.contact_email || "—"}
                </td>
                <td className="px-4 py-3">{item.payment_terms || "—"}</td>
                <td className="px-4 py-3">
                  <span
                    className={`badge capitalize ${
                      item.lifecycle_status === "active"
                        ? "bg-green-100 text-green-700"
                        : item.lifecycle_status === "offboarded" || item.lifecycle_status === "merged"
                        ? "bg-slate-100 text-slate-500"
                        : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {(item.lifecycle_status ?? (item.is_active ? "active" : "inactive")).replace(/_/g, " ")}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
