"use client";

import { useEffect, useState } from "react";
import { extractErrorMessage, listCatalogItems } from "@/lib/api";
import type { CatalogItem } from "@/lib/types";

export default function CatalogQuickAdd({
  onQuickAdd,
}: {
  onQuickAdd: (item: CatalogItem) => void;
}) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);

  useEffect(() => {
    listCatalogItems()
      .then((res) => setItems(res.items))
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  function handleAdd(item: CatalogItem) {
    onQuickAdd(item);
    setAdded(item.id);
    window.setTimeout(() => setAdded(null), 1500);
  }

  if (loading) {
    return <p className="text-sm text-slate-500">Loading catalog…</p>;
  }

  if (error) {
    return <p className="text-sm text-red-600">Couldn&apos;t load catalog: {error}</p>;
  }

  if (items.length === 0) {
    return <p className="text-sm text-slate-500">No catalog items available.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
        >
          <div className="flex h-32 items-center justify-center bg-slate-50">
            {item.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.image_url} alt={item.name} className="h-full w-full object-cover" />
            ) : (
              <span className="text-3xl text-slate-300">📦</span>
            )}
          </div>
          <div className="flex flex-1 flex-col gap-1.5 p-3">
            <p className="text-sm font-semibold text-slate-900">{item.name}</p>
            {item.category && (
              <span className="w-fit rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                {item.category}
              </span>
            )}
            {item.supplier_name && (
              <p className="text-xs text-slate-500">Supplier: {item.supplier_name}</p>
            )}
            <p className="text-sm font-semibold text-slate-900">
              {Number(item.unit_price).toLocaleString("en-US", {
                style: "currency",
                currency: item.currency || "USD",
              })}
            </p>
            {item.account_code && (
              <p className="text-xs font-mono text-slate-400">GL: {item.account_code}</p>
            )}
            <button
              type="button"
              onClick={() => handleAdd(item)}
              className={`mt-auto rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                added === item.id
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-brand-600 text-white hover:bg-brand-700"
              }`}
            >
              {added === item.id ? "✓ Added" : "Quick add"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
