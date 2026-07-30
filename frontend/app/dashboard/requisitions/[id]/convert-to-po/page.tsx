"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getRequisition,
  listSuppliers,
  listMyAddresses,
  convertRequisitionToPurchaseOrder,
  extractErrorMessage,
} from "@/lib/api";
import type { AddressResult, Requisition, Supplier } from "@/lib/types";
import CommodityCodeInput from "@/components/CommodityCodeInput";

interface PoLineItemDraft {
  description: string;
  quantity: string;
  unit_price: string;
  commodity_code: string;
  account_code: string;
}

function fromRequisitionLine(li: Requisition["line_items"][number]): PoLineItemDraft {
  return {
    description: li.description,
    quantity: li.quantity,
    unit_price: li.unit_price ?? "",
    commodity_code: li.commodity ?? "",
    account_code: li.account_code ?? "",
  };
}

function emptyLine(): PoLineItemDraft {
  return { description: "", quantity: "1", unit_price: "", commodity_code: "", account_code: "" };
}

export default function ConvertToPurchaseOrderPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [requisition, setRequisition] = useState<Requisition | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [addresses, setAddresses] = useState<AddressResult[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [form, setForm] = useState({
    supplier_id: "",
    currency: "USD",
    shipping_amount: "",
    shipping_allocation_method: "prorate_by_value",
    ship_to_address_id: "",
    bill_to_address_id: "",
    incoterms: "",
    payment_terms: "",
    notes: "",
  });
  const [lineItems, setLineItems] = useState<PoLineItemDraft[]>([emptyLine()]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [req, supplierRes, addressList] = await Promise.all([
          getRequisition(params.id),
          listSuppliers(),
          listMyAddresses(),
        ]);
        setRequisition(req);
        setSuppliers(supplierRes.items);
        setAddresses(addressList);
        setForm((f) => ({
          ...f,
          currency: req.currency || "USD",
          supplier_id: req.supplier_id || f.supplier_id,
        }));
        if (req.line_items && req.line_items.length > 0) {
          setLineItems(req.line_items.map(fromRequisitionLine));
        }
      } catch (err) {
        setLoadError(extractErrorMessage(err));
      } finally {
        setLoaded(true);
      }
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  function updateLine(index: number, patch: Partial<PoLineItemDraft>) {
    setLineItems((items) => items.map((li, i) => (i === index ? { ...li, ...patch } : li)));
  }

  function addLine() {
    setLineItems((items) => [...items, emptyLine()]);
  }

  function removeLine(index: number) {
    setLineItems((items) => items.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.supplier_id) {
      setError("Supplier is required.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const rows = lineItems.filter((li) => li.description.trim());
      const po = await convertRequisitionToPurchaseOrder(params.id, {
        supplier_id: form.supplier_id,
        currency: form.currency,
        notes: form.notes || undefined,
        line_items: rows.map((li) => ({
          description: li.description,
          quantity: Number(li.quantity) || 1,
          unit_price: li.unit_price ? Number(li.unit_price) : undefined,
          // commodity_code drives GL account auto-resolution server-side;
          // commodity_code_free_text is what actually persists on the line for
          // display, so both are sent with the same value.
          commodity_code: li.commodity_code || undefined,
          commodity_code_free_text: li.commodity_code || undefined,
          account_code: li.account_code || undefined,
        })),
        shipping_amount: form.shipping_amount || undefined,
        shipping_allocation_method: form.shipping_allocation_method || undefined,
        ship_to_address_id: form.ship_to_address_id || undefined,
        bill_to_address_id: form.bill_to_address_id || undefined,
        incoterms: form.incoterms || undefined,
        payment_terms: form.payment_terms || undefined,
      });
      router.replace(`/dashboard/purchase-orders/${po.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!loaded) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  if (loadError || !requisition) {
    return <p className="text-sm text-red-600">{loadError || "Requisition not found."}</p>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <button
          onClick={() => router.push(`/dashboard/requisitions/${params.id}`)}
          className="text-sm text-brand-600 hover:underline"
        >
          &larr; Back to requisition
        </button>
        <h1 className="mt-2 text-2xl font-semibold">Convert to Purchase Order</h1>
        <p className="text-sm text-slate-500">
          From requisition {requisition.requisition_number || requisition.title}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="card space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="supplier">
                Supplier
              </label>
              <select
                id="supplier"
                required
                className="input-field"
                value={form.supplier_id}
                onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
              >
                <option value="">Select a supplier...</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="currency">
                Currency
              </label>
              <input
                id="currency"
                maxLength={3}
                className="input-field"
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="ship_to">
                Ship to
              </label>
              <select
                id="ship_to"
                className="input-field"
                value={form.ship_to_address_id}
                onChange={(e) => setForm({ ...form, ship_to_address_id: e.target.value })}
              >
                <option value="">None selected</option>
                {addresses.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                    {a.address_line1 ? ` — ${a.address_line1}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="bill_to">
                Bill to
              </label>
              <select
                id="bill_to"
                className="input-field"
                value={form.bill_to_address_id}
                onChange={(e) => setForm({ ...form, bill_to_address_id: e.target.value })}
              >
                <option value="">None selected</option>
                {addresses.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                    {a.address_line1 ? ` — ${a.address_line1}` : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="shipping_amount">
                Shipping amount
              </label>
              <input
                id="shipping_amount"
                type="number"
                min="0"
                step="0.01"
                className="input-field"
                value={form.shipping_amount}
                onChange={(e) => setForm({ ...form, shipping_amount: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="shipping_allocation_method">
                Shipping allocation
              </label>
              <select
                id="shipping_allocation_method"
                className="input-field"
                value={form.shipping_allocation_method}
                onChange={(e) => setForm({ ...form, shipping_allocation_method: e.target.value })}
              >
                <option value="prorate_by_value">Prorate by line value</option>
                <option value="prorate_by_weight">Prorate by weight</option>
                <option value="single_line">All on last line</option>
                <option value="manual">Manual (set per line later)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label" htmlFor="incoterms">
                Incoterms
              </label>
              <input
                id="incoterms"
                className="input-field"
                placeholder="e.g. DAP, FOB"
                value={form.incoterms}
                onChange={(e) => setForm({ ...form, incoterms: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="payment_terms">
                Payment terms
              </label>
              <input
                id="payment_terms"
                className="input-field"
                placeholder="e.g. Net 30"
                value={form.payment_terms}
                onChange={(e) => setForm({ ...form, payment_terms: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="label" htmlFor="notes">
              Notes
            </label>
            <textarea
              id="notes"
              className="input-field"
              rows={2}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
        </div>

        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Line items</h2>
            <button type="button" className="btn-secondary" onClick={addLine}>
              + Add line
            </button>
          </div>
          {requisition.line_items && requisition.line_items.length > 0 && (
            <p className="text-sm text-slate-500">
              Pre-filled from the requisition&apos;s line items — edit or remove as needed.
            </p>
          )}
          <div className="space-y-4">
            {lineItems.map((li, index) => (
              <div
                key={index}
                className="grid grid-cols-12 gap-3 border-b border-slate-100 pb-4 last:border-0 last:pb-0"
              >
                <div className="col-span-12 sm:col-span-4">
                  <label className="label">Description</label>
                  <input
                    className="input-field"
                    value={li.description}
                    onChange={(e) => updateLine(index, { description: e.target.value })}
                  />
                </div>
                <div className="col-span-4 sm:col-span-1">
                  <label className="label">Qty</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-field"
                    value={li.quantity}
                    onChange={(e) => updateLine(index, { quantity: e.target.value })}
                  />
                </div>
                <div className="col-span-8 sm:col-span-2">
                  <label className="label">Unit price</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-field"
                    value={li.unit_price}
                    onChange={(e) => updateLine(index, { unit_price: e.target.value })}
                  />
                </div>
                <div className="col-span-12 sm:col-span-3">
                  <label className="label">Commodity code</label>
                  <CommodityCodeInput
                    value={li.commodity_code}
                    onChange={(value) => updateLine(index, { commodity_code: value })}
                  />
                </div>
                <div className="col-span-8 sm:col-span-2">
                  <label className="label">Account code override</label>
                  <input
                    className="input-field"
                    placeholder="Auto from commodity if blank"
                    value={li.account_code}
                    onChange={(e) => updateLine(index, { account_code: e.target.value })}
                  />
                </div>
                <div className="col-span-4 flex items-end sm:col-span-12 sm:justify-end">
                  <button
                    type="button"
                    className="text-sm text-red-600 hover:underline"
                    onClick={() => removeLine(index)}
                    disabled={lineItems.length === 1}
                  >
                    Remove line
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-3">
          <button type="submit" disabled={submitting} className="btn-primary">
            {submitting ? "Creating..." : "Create purchase order"}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => router.push(`/dashboard/requisitions/${params.id}`)}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
