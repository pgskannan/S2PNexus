"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  addRequisitionLineItem,
  createRequisition,
  extractErrorMessage,
  listCatalogItems,
  listSuppliers,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { CatalogItem, Supplier } from "@/lib/types";

// 3-click minimum PR creation (backlog Section 5): 1. select item,
// 2. select supplier, 3. submit. A distinct fast-path next to the full wizard,
// which is still there for non-catalog / custom requisitions.
export default function QuickCreateRequisitionPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [selected, setSelected] = useState<CatalogItem | null>(null);
  const [supplierId, setSupplierId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listCatalogItems(), listSuppliers()])
      .then(([catRes, supRes]) => {
        setItems(catRes.items);
        setSuppliers(supRes.items);
      })
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  function pickItem(item: CatalogItem) {
    setSelected(item);
    // Default the supplier to the catalog item's preferred supplier.
    setSupplierId(item.supplier_id || "");
    setStep(2);
  }

  function selectedSupplier(): Supplier | undefined {
    return suppliers.find((s) => s.id === supplierId);
  }

  async function handleSubmit() {
    if (!user || !selected) return;
    if (!supplierId) {
      setError("Please select a supplier.");
      setStep(2);
      return;
    }
    const supplier = selectedSupplier();
    if (supplier && (!supplier.is_active || !supplier.contact_email)) {
      setError(
        !supplier.is_active
          ? "This supplier is inactive — PO auto-creation will be blocked after approval. Choose an active supplier."
          : "This supplier has no contact email on file — PO auto-creation will be blocked after approval. Ask an admin to add one, or choose a different supplier."
      );
      setStep(2);
      return;
    }
    // 2026-08-05: quick-create has no field to type a GL/account code in --
    // it only ever comes from the catalog item. If that item has none on
    // file, the PR would submit fine but silently land in an unrecoverable
    // "Exception" status once approved (PO auto-creation gate blocks on a
    // missing account code). Better to block it here with a clear reason
    // than let the requester discover it days later.
    if (!selected.account_code) {
      setError(
        `"${selected.name}" has no GL/account code on file, so its PO can't be created automatically after approval. Use the full wizard to add one, or ask an admin to set it on this catalog item.`
      );
      setStep(3);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const requisition = await createRequisition({
        title: selected.name,
        request_type: "catalog",
        supplier_id: supplierId,
        currency: selected.currency || "USD",
        estimated_value: selected.unit_price,
        category: selected.category || undefined,
        commodity: selected.commodity || undefined,
        notes: `Quick-created from catalog item "${selected.name}".`,
        requested_by: user.id,
      });
      const price = Number(selected.unit_price) || 0;
      await addRequisitionLineItem(requisition.id, {
        description: selected.description || selected.name,
        quantity: "1",
        unit_price: selected.unit_price,
        line_total: price.toFixed(2),
        commodity: selected.commodity || undefined,
        category: selected.category || undefined,
        account_code: selected.account_code || undefined,
      });
      router.replace(`/dashboard/requisitions/${requisition.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-slate-400">Loading catalog…</p>;
  if (error && items.length === 0) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-red-600">{error}</p>
        <Link href="/dashboard/requisitions/new" className="text-sm text-brand-600 hover:underline">
          &larr; Use the full wizard instead
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Quick Create PR</h1>
        <Link href="/dashboard/requisitions/new" className="text-sm text-brand-600 hover:underline">
          Full wizard &rarr;
        </Link>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-2 text-sm">
        {(["Select item", "Select supplier", "Submit PR"] as const).map((label, i) => {
          const n = (i + 1) as 1 | 2 | 3;
          const active = step === n;
          const done = step > n;
          return (
            <div key={label} className="flex items-center gap-2">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                  active ? "bg-brand-600 text-white" : done ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-400"
                }`}
              >
                {done ? "✓" : n}
              </span>
              <span className={active ? "font-medium text-slate-900" : "text-slate-500"}>{label}</span>
              {n < 3 && <span className="mx-1 h-0.5 w-6 bg-slate-200" />}
            </div>
          );
        })}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {step === 1 && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">Step 1 of 3 — pick an item to request.</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {items.map((item) => (
              <button
                key={item.id}
                onClick={() => pickItem(item)}
                className="flex overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-sm transition-colors hover:border-brand-400 hover:bg-slate-50"
              >
                <div className="flex h-24 w-24 shrink-0 items-center justify-center bg-slate-50">
                  {item.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.image_url} alt={item.name} className="h-full w-full object-cover" />
                  ) : (
                    <span className="text-2xl text-slate-300">📦</span>
                  )}
                </div>
                <div className="flex flex-1 flex-col gap-1 p-3">
                  <span className="text-sm font-semibold text-slate-900">{item.name}</span>
                  {item.category && (
                    <span className="w-fit rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700">
                      {item.category}
                    </span>
                  )}
                  <span className="text-sm font-semibold text-slate-900">
                    {Number(item.unit_price).toLocaleString("en-US", {
                      style: "currency",
                      currency: item.currency || "USD",
                    })}
                  </span>
                  <span className="text-xs text-slate-500">{item.supplier_name ?? "No supplier"}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 2 && selected && (
        <div className="card space-y-4">
          <p className="text-sm text-slate-500">Step 2 of 3 — confirm the supplier for this item.</p>
          <div className="rounded-md bg-slate-50 p-3 text-sm">
            <p className="font-semibold text-slate-900">{selected.name}</p>
            <p className="text-xs text-slate-500">
              {selected.description} · {selected.category ?? "No category"} ·{" "}
              {Number(selected.unit_price).toLocaleString("en-US", {
                style: "currency",
                currency: selected.currency || "USD",
              })}
            </p>
          </div>
          <div>
            <label className="label" htmlFor="quick-supplier">
              Supplier
            </label>
            <select
              id="quick-supplier"
              className="input-field"
              value={supplierId}
              onChange={(e) => setSupplierId(e.target.value)}
            >
              <option value="">Select a supplier…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-between">
            <button type="button" className="btn-secondary" onClick={() => setStep(1)}>
              Back
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!supplierId}
              onClick={() => setStep(3)}
            >
              Review & submit
            </button>
          </div>
        </div>
      )}

      {step === 3 && selected && (
        <div className="card space-y-4">
          <p className="text-sm text-slate-500">Step 3 of 3 — review and submit.</p>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-slate-500">Item</dt>
              <dd className="font-medium text-slate-900">{selected.name}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Supplier</dt>
              <dd className="font-medium text-slate-900">{selectedSupplier()?.name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Quantity</dt>
              <dd>1</dd>
            </div>
            <div>
              <dt className="text-slate-500">Unit price</dt>
              <dd>
                {Number(selected.unit_price).toLocaleString("en-US", {
                  style: "currency",
                  currency: selected.currency || "USD",
                })}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Category</dt>
              <dd>{selected.category ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">GL account</dt>
              <dd className="font-mono">{selected.account_code ?? "—"}</dd>
            </div>
          </dl>
          {!selected.account_code && (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              This item has no GL/account code on file. Submitting is blocked -- use the full wizard instead, or ask
              an admin to set one on this catalog item.
            </p>
          )}
          <div className="flex justify-between">
            <button type="button" className="btn-secondary" onClick={() => setStep(2)}>
              Back
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={busy || !selected.account_code}
              onClick={handleSubmit}
            >
              {busy ? "Creating…" : "Submit PR"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
