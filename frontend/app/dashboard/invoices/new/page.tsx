"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  createInvoice,
  extractErrorMessage,
  listInvoices,
  listPurchaseOrders,
  listSuppliers,
  type InvoiceCreate,
} from "@/lib/api";
import type { ProcurementInvoice, PurchaseOrder, Supplier } from "@/lib/types";

type Mode = "po" | "nonpo";

interface InvoiceLineEdit {
  purchase_order_line_item_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
}

const toFixed = (n: number) => n.toFixed(2);

export default function NewInvoicePage() {
  const [mode, setMode] = useState<Mode>("po");
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [existingInvoiceNumbers, setExistingInvoiceNumbers] = useState<string[]>([]);
  const [selectedPoId, setSelectedPoId] = useState("");
  const [selectedPo, setSelectedPo] = useState<PurchaseOrder | null>(null);
  // Set when this page was opened from a specific PO (e.g. the "Invoice" tab
  // or "+ New Invoice" from a PO-scoped list) via ?po=<id> -- the PO is then
  // auto-bound and the picker is replaced with a read-only reference instead
  // of asking the user to find and re-select the same PO.
  const [lockedPoId, setLockedPoId] = useState<string | null>(null);
  const [lines, setLines] = useState<InvoiceLineEdit[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [description, setDescription] = useState("");
  const [memoAmount, setMemoAmount] = useState("");
  const [memoTax, setMemoTax] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ProcurementInvoice | null>(null);

  useEffect(() => {
    const poParam = new URLSearchParams(window.location.search).get("po");
    if (poParam) setLockedPoId(poParam);

    Promise.all([
      listPurchaseOrders({ limit: 500 }),
      listSuppliers(),
      listInvoices(),
    ])
      .then(([poRes, supRes, invRes]) => {
        setPurchaseOrders(poRes.items);
        setSuppliers(supRes.items);
        setExistingInvoiceNumbers(invRes.items.map((i) => i.invoice_number));
        if (poParam) {
          setMode("po");
          handleSelectPo(poParam, poRes.items);
        }
      })
      .catch((err) => setError(extractErrorMessage(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSelectPo(id: string, source: PurchaseOrder[] = purchaseOrders) {
    setSelectedPoId(id);
    const po = source.find((p) => p.id === id) ?? null;
    setSelectedPo(po);
    if (po) {
      setLines(
        po.line_items.map((li) => ({
          purchase_order_line_item_id: li.id,
          description: li.description,
          quantity: li.quantity ?? "0",
          unit_price: li.unit_price ?? "0",
          tax_amount: "0",
        }))
      );
      if (po.currency) setCurrency(po.currency);
    } else {
      setLines([]);
    }
  }

  const amounts = useMemo(() => {
    let subtotal = 0;
    let tax = 0;
    for (const l of lines) {
      const qty = Number(l.quantity) || 0;
      const price = Number(l.unit_price) || 0;
      subtotal += qty * price;
      tax += Number(l.tax_amount) || 0;
    }
    return { subtotal, tax, total: subtotal + tax };
  }, [lines]);

  async function handleSubmitPo() {
    setBusy(true);
    setError(null);
    try {
      const payload: InvoiceCreate = {
        supplier_id: selectedPo?.supplier_id ?? null,
        purchase_order_id: selectedPoId,
        amount: toFixed(amounts.subtotal),
        tax_amount: toFixed(amounts.tax),
        total_amount: toFixed(amounts.total),
        currency,
        line_items: lines.map((l) => ({
          purchase_order_line_item_id: l.purchase_order_line_item_id,
          description: l.description,
          quantity: l.quantity || "0",
          unit_price: l.unit_price || "0",
          line_total: toFixed((Number(l.quantity) || 0) * (Number(l.unit_price) || 0)),
          tax_amount: l.tax_amount || "0",
        })),
      };
      const inv = await createInvoice(payload);
      setCreated(inv);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitNonPo() {
    setBusy(true);
    setError(null);
    try {
      const amount = Number(memoAmount) || 0;
      const tax = Number(memoTax) || 0;
      const payload: InvoiceCreate = {
        supplier_id: supplierId || null,
        amount: toFixed(amount),
        tax_amount: toFixed(tax),
        total_amount: toFixed(amount + tax),
        currency,
        description: description || undefined,
      };
      const inv = await createInvoice(payload);
      setCreated(inv);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (created) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <div className="card space-y-3">
          <h1 className="text-xl font-semibold">Invoice created</h1>
          <p className="text-sm text-slate-600">
            Invoice <span className="font-mono font-medium">{created.invoice_number}</span> was
            created successfully.
          </p>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-slate-500">Status</dt>
              <dd className="capitalize">{created.status}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Match status</dt>
              <dd className="capitalize">{created.match_status}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Amount</dt>
              <dd>
                {created.currency} {created.amount}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Total</dt>
              <dd>
                {created.currency} {created.total_amount ?? created.amount}
              </dd>
            </div>
          </dl>
          <div className="flex gap-2 pt-2">
            <Link href={`/dashboard/invoices?po=${created.purchase_order_id ?? ""}`} className="btn-primary">
              View invoices
            </Link>
            <button type="button" className="btn-secondary" onClick={() => setCreated(null)}>
              Create another
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Create invoice</h1>
        <p className="mt-1 text-sm text-slate-500">
          Create a PO-linked invoice (loads PO line items) or a non-PO (memo) invoice.
        </p>
      </div>

      <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
        {(
          [
            { key: "po", label: "PO invoice" },
            { key: "nonpo", label: "Non-PO invoice" },
          ] as { key: Mode; label: string }[]
        ).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setMode(t.key)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              mode === t.key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {mode === "po" ? (
        <div className="card space-y-4">
          <div>
            <label className="text-xs text-slate-500">Purchase order</label>
            {lockedPoId ? (
              <div className="input-field flex items-center justify-between bg-slate-50 text-slate-700">
                <span className="font-mono">
                  {selectedPo?.order_number ?? lockedPoId}
                  {selectedPo && ` · ${selectedPo.lifecycle_status} · ${selectedPo.currency} ${selectedPo.grand_total ?? selectedPo.total_amount ?? ""}`}
                </span>
                <button
                  type="button"
                  className="text-xs font-medium text-brand-700 underline"
                  onClick={() => {
                    setLockedPoId(null);
                    handleSelectPo("");
                  }}
                >
                  Change
                </button>
              </div>
            ) : (
              <select className="input-field" value={selectedPoId} onChange={(e) => handleSelectPo(e.target.value)}>
                <option value="">Select a purchase order...</option>
                {purchaseOrders.map((po) => (
                  <option key={po.id} value={po.id}>
                    {po.order_number} · {po.lifecycle_status} · {po.currency} {po.grand_total ?? po.total_amount ?? ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          {selectedPo && (
            <>
              <div className="text-sm text-slate-600">
                <span className="font-medium">Currency:</span> {currency} — invoice number is
                auto-generated on save.
              </div>
              {lines.length === 0 ? (
                <p className="text-sm text-slate-400">This purchase order has no line items.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-slate-500">
                        <th className="py-2 pr-3">Description</th>
                        <th className="py-2 pr-3">Qty</th>
                        <th className="py-2 pr-3">Unit price</th>
                        <th className="py-2 pr-3">Tax</th>
                        <th className="py-2 pr-3 text-right">Line total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((line, idx) => {
                        const lineTotal = (Number(line.quantity) || 0) * (Number(line.unit_price) || 0);
                        return (
                          <tr key={line.purchase_order_line_item_id} className="border-b border-slate-50 last:border-0">
                            <td className="py-2 pr-3">{line.description}</td>
                            <td className="py-2 pr-3">
                              <input
                                className="input-field w-20"
                                type="number"
                                min="0"
                                step="any"
                                value={line.quantity}
                                onChange={(e) =>
                                  setLines((cur) => cur.map((l, i) => (i === idx ? { ...l, quantity: e.target.value } : l)))
                                }
                              />
                            </td>
                            <td className="py-2 pr-3">
                              <input
                                className="input-field w-24"
                                type="number"
                                min="0"
                                step="any"
                                value={line.unit_price}
                                onChange={(e) =>
                                  setLines((cur) => cur.map((l, i) => (i === idx ? { ...l, unit_price: e.target.value } : l)))
                                }
                              />
                            </td>
                            <td className="py-2 pr-3">
                              <input
                                className="input-field w-24"
                                type="number"
                                min="0"
                                step="any"
                                value={line.tax_amount}
                                onChange={(e) =>
                                  setLines((cur) => cur.map((l, i) => (i === idx ? { ...l, tax_amount: e.target.value } : l)))
                                }
                              />
                            </td>
                            <td className="py-2 pr-3 text-right">{toFixed(lineTotal)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <dl className="grid grid-cols-3 gap-4 border-t border-slate-100 pt-3 text-sm">
                <div>
                  <dt className="text-slate-500">Subtotal</dt>
                  <dd className="font-medium">
                    {currency} {toFixed(amounts.subtotal)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Tax</dt>
                  <dd className="font-medium">
                    {currency} {toFixed(amounts.tax)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Total</dt>
                  <dd className="font-semibold">
                    {currency} {toFixed(amounts.total)}
                  </dd>
                </div>
              </dl>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={busy || lines.length === 0 || amounts.total <= 0}
                  onClick={handleSubmitPo}
                  className="btn-primary"
                >
                  {busy ? "Creating..." : "Create invoice"}
                </button>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="card space-y-4">
          <div>
            <label className="text-xs text-slate-500">Supplier</label>
            <select className="input-field" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="">Select a supplier...</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-500">Description</label>
            <input
              className="input-field"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Consulting services — March"
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-slate-500">Amount</label>
              <input
                className="input-field"
                type="number"
                min="0"
                step="any"
                value={memoAmount}
                onChange={(e) => setMemoAmount(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="text-xs text-slate-500">Tax</label>
              <input
                className="input-field"
                type="number"
                min="0"
                step="any"
                value={memoTax}
                onChange={(e) => setMemoTax(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="text-xs text-slate-500">Currency</label>
              <input className="input-field" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} />
            </div>
          </div>
          <p className="text-xs text-slate-400">
            Non-PO invoices are blocked for approval until approved via the invoice approval workflow.
          </p>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end">
            <button type="button" disabled={busy} onClick={handleSubmitNonPo} className="btn-primary">
              {busy ? "Creating..." : "Create invoice"}
            </button>
          </div>
        </div>
      )}

      <p className="text-xs text-slate-400">
        {existingInvoiceNumbers.length > 0
          ? `Existing invoice numbers: ${existingInvoiceNumbers.slice(-5).join(", ")}${existingInvoiceNumbers.length > 5 ? "…" : ""}`
          : ""}
      </p>
    </div>
  );
}
