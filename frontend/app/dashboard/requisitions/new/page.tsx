"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createRequisition, addRequisitionLineItem, extractErrorMessage, listSuppliers } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import CommodityCodeInput from "@/components/CommodityCodeInput";
import CategoryInput from "@/components/CategoryInput";
import type { Supplier } from "@/lib/types";

interface LineItemDraft {
  description: string;
  quantity: string;
  unit_price: string;
  commodity: string;
  category: string;
  account_code: string;
}

function emptyLineItem(): LineItemDraft {
  return {
    description: "",
    quantity: "1",
    unit_price: "",
    commodity: "",
    category: "",
    account_code: "",
  };
}

const STEPS = [
  { n: 1, label: "Header" },
  { n: 2, label: "Line Items" },
  { n: 3, label: "Summary & Submit" },
] as const;

function lineTotal(li: LineItemDraft): number {
  const qty = Number(li.quantity) || 0;
  const price = Number(li.unit_price) || 0;
  return qty * price;
}

export default function NewRequisitionPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [form, setForm] = useState({
    title: "",
    description: "",
    supplier_id: "",
    request_type: "catalog",
    currency: "USD",
    estimated_value: "",
    priority: "medium",
    commodity: "",
    category: "",
    need_by_date: "",
    is_emergency: false,
    delay_until: "",
    header_tax: "",
    shipping_cost: "",
    notes: "",
  });
  const [lineItems, setLineItems] = useState<LineItemDraft[]>([emptyLineItem()]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lineItemWarning, setLineItemWarning] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listSuppliers()
      .then((res) => setSuppliers(res.items))
      .catch(() => setSuppliers([]));
  }, []);

  const titleValid = form.title.trim().length > 0;
  const rowsToSubmit = lineItems.filter((li) => li.description.trim());
  const linesSubtotal = rowsToSubmit.reduce((sum, li) => sum + lineTotal(li), 0);
  const headerTax = Number(form.header_tax) || 0;
  const shippingCost = Number(form.shipping_cost) || 0;
  const computedGrandTotal = linesSubtotal + headerTax + shippingCost;
  const lineItemValidation = lineItems.map((li) => {
    const hasContent =
      li.description.trim() ||
      li.unit_price.trim() ||
      li.category.trim() ||
      li.commodity.trim() ||
      li.account_code.trim() ||
      li.quantity !== "1";

    const errors: { description?: string; unit_price?: string; category?: string } = {};
    if (hasContent) {
      if (!li.description.trim()) {
        errors.description = "Description is required.";
      }
      if (!li.category.trim()) {
        errors.category = "Category is required.";
      }
      if (!li.unit_price || Number(li.unit_price) <= 0) {
        errors.unit_price = "Unit price must be greater than zero.";
      }
    }
    return errors;
  });
  const hasLineItemValidationErrors = lineItemValidation.some((errors) => Object.keys(errors).length > 0);

  function updateLineItem(index: number, patch: Partial<LineItemDraft>) {
    setLineItems((items) => items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  function addRow() {
    setLineItems((items) => [...items, emptyLineItem()]);
  }

  function removeRow(index: number) {
    setLineItems((items) => items.filter((_, i) => i !== index));
  }

  function goToStep(target: 1 | 2 | 3) {
    // Free navigation between steps -- nothing already entered is lost by
    // moving around, so the only gate is not letting Next/step-2/step-3 be
    // reached without a title (the one truly required field).
    if (target > 1 && !titleValid) {
      setError("Title is required before continuing.");
      setStep(1);
      return;
    }
    if (target === 3 && hasLineItemValidationErrors) {
      setError("Please complete the highlighted line-item fields before continuing.");
      setStep(2);
      return;
    }
    setError(null);
    setStep(target);
  }

  async function handleSubmit() {
    if (!user) return;
    if (!titleValid) {
      setError("Title is required.");
      setStep(1);
      return;
    }
    if (!form.estimated_value || Number(form.estimated_value) <= 0) {
      setError("Estimated value is required — the approval flow routes on it (estimated cost, not line-item totals).");
      setStep(1);
      return;
    }
    setError(null);
    setLineItemWarning(null);
    setLoading(true);
    try {
      const requisition = await createRequisition({
        title: form.title,
        description: form.description || undefined,
        supplier_id: form.supplier_id || undefined,
        request_type: form.request_type,
        currency: form.currency,
        estimated_value: form.estimated_value ? form.estimated_value : undefined,
        priority: form.priority,
        commodity: form.commodity || undefined,
        category: form.category || undefined,
        need_by_date: form.need_by_date ? new Date(form.need_by_date).toISOString() : undefined,
        is_emergency: form.is_emergency,
        delay_until: form.delay_until ? new Date(form.delay_until).toISOString() : undefined,
        header_tax: form.header_tax || undefined,
        shipping_cost: form.shipping_cost || undefined,
        notes: form.notes || undefined,
        requested_by: user.id,
      });

      // Line items are added one at a time against the already-created
      // requisition (there's no combined create-with-line-items endpoint for
      // requisitions, unlike purchase orders).
      let failedCount = 0;
      for (const li of rowsToSubmit) {
        const quantity = li.quantity ? Number(li.quantity) : 1;
        const unitPrice = li.unit_price ? Number(li.unit_price) : undefined;
        const total = unitPrice !== undefined ? (quantity * unitPrice).toFixed(2) : undefined;
        try {
          await addRequisitionLineItem(requisition.id, {
            description: li.description,
            quantity: li.quantity || "1",
            unit_price: li.unit_price || undefined,
            line_total: total,
            commodity: li.commodity || undefined,
            category: li.category || undefined,
            account_code: li.account_code || undefined,
          });
        } catch {
          failedCount += 1;
        }
      }
      if (failedCount > 0) {
        setLineItemWarning(
          `Requisition created, but ${failedCount} line item(s) failed to save. You can retry from the detail page.`
        );
      }
      router.replace(`/dashboard/requisitions/${requisition.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-5xl space-y-6">
      <h1 className="text-2xl font-semibold">New Requisition</h1>

      {/* Top progress bar */}
      <div className="flex items-center">
        {STEPS.map((s, i) => (
          <div key={s.n} className="flex flex-1 items-center last:flex-none">
            <button
              type="button"
              onClick={() => goToStep(s.n)}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-medium ${
                step === s.n
                  ? "bg-brand-600 text-white"
                  : step > s.n
                  ? "bg-brand-100 text-brand-700"
                  : "bg-slate-100 text-slate-400"
              }`}
            >
              {step > s.n ? "✓" : s.n}
            </button>
            <span className={`ml-2 whitespace-nowrap text-sm ${step === s.n ? "font-semibold text-slate-900" : "text-slate-500"}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`mx-3 h-0.5 flex-1 ${step > s.n ? "bg-brand-300" : "bg-slate-200"}`} />
            )}
          </div>
        ))}
      </div>

      <div className="flex gap-6">
        {/* Left step sub-menu */}
        <aside className="w-44 shrink-0 space-y-1">
          {STEPS.map((s) => (
            <button
              key={s.n}
              type="button"
              onClick={() => goToStep(s.n)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm font-medium ${
                step === s.n ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {s.n}. {s.label}
            </button>
          ))}
        </aside>

        {/* Step content */}
        <div className="max-w-3xl flex-1 space-y-6">
          {error && <p className="text-sm text-red-600">{error}</p>}
          {lineItemWarning && <p className="text-sm text-amber-600">{lineItemWarning}</p>}

          {step === 1 && (
            <div className="card space-y-4">
              <div>
                <label className="label" htmlFor="title">
                  Title
                </label>
                <input
                  id="title"
                  required
                  placeholder="e.g. Laptops for new engineering hires"
                  className="input-field"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                />
              </div>
              <div>
                <label className="label" htmlFor="description">
                  Business Purpose / Justification
                </label>
                <textarea
                  id="description"
                  placeholder="Business justification for this request"
                  className="input-field"
                  rows={3}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </div>
              <div>
                <label className="label" htmlFor="supplier_id" title="Who this requisition will be ordered from — required before it can convert to a PO">
                  Supplier
                </label>
                <select
                  id="supplier_id"
                  className="input-field"
                  value={form.supplier_id}
                  onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
                >
                  <option value="">Select a supplier (optional at this stage)...</option>
                  {suppliers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label" htmlFor="priority">
                    Priority
                  </label>
                  <select
                    id="priority"
                    className="input-field"
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: e.target.value })}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="request_type">
                    Request type
                  </label>
                  <select
                    id="request_type"
                    className="input-field"
                    value={form.request_type}
                    onChange={(e) => setForm({ ...form, request_type: e.target.value })}
                  >
                    <option value="catalog">Catalog</option>
                    <option value="non_catalog">Non-catalog</option>
                    <option value="service">Service</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label" htmlFor="estimated_value">
                    Estimated value
                  </label>
                  <input
                    id="estimated_value"
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    className="input-field"
                    value={form.estimated_value}
                    onChange={(e) => setForm({ ...form, estimated_value: e.target.value })}
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Drives the approval flow — thresholds compare this estimated cost, not line-item totals.
                  </p>
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
                  <label className="label" htmlFor="commodity">
                    Commodity (overall)
                  </label>
                  <CommodityCodeInput
                    id="commodity"
                    value={form.commodity}
                    onChange={(value) => setForm({ ...form, commodity: value })}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="category" title="Classifies this line for spend reporting and GL mapping">
                    Category
                  </label>
                  <CategoryInput
                    id="category"
                    value={form.category}
                    placeholder="e.g. IT Hardware"
                    onChange={(value) => setForm({ ...form, category: value })}
                  />
                </div>
              </div>
              <div>
                <label className="label" htmlFor="need_by_date">
                  Need-by date
                </label>
                <input
                  id="need_by_date"
                  type="date"
                  className="input-field"
                  value={form.need_by_date}
                  onChange={(e) => setForm({ ...form, need_by_date: e.target.value })}
                />
              </div>

              <div className="rounded-md border border-slate-200 p-4">
                <div className="flex items-center gap-2">
                  <input
                    id="is_emergency"
                    type="checkbox"
                    checked={form.is_emergency}
                    onChange={(e) => setForm({ ...form, is_emergency: e.target.checked })}
                  />
                  <label htmlFor="is_emergency" className="text-sm font-medium">
                    Emergency Buy -- urgent, bypasses standard lead times
                  </label>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-4">
                  <div>
                    <label className="label" htmlFor="delay_until">
                      Delay until
                    </label>
                    <input
                      id="delay_until"
                      type="date"
                      className="input-field"
                      value={form.delay_until}
                      onChange={(e) => setForm({ ...form, delay_until: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor="header_tax">
                      Header tax
                    </label>
                    <input
                      id="header_tax"
                      type="number"
                      min="0"
                      step="0.01"
                      className="input-field"
                      value={form.header_tax}
                      onChange={(e) => setForm({ ...form, header_tax: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor="shipping_cost">
                      Shipping cost
                    </label>
                    <input
                      id="shipping_cost"
                      type="number"
                      min="0"
                      step="0.01"
                      className="input-field"
                      value={form.shipping_cost}
                      onChange={(e) => setForm({ ...form, shipping_cost: e.target.value })}
                    />
                  </div>
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
              <p className="text-xs text-slate-400">
                Header attachments (quotes, approval emails) can be added from the requisition detail page after it&apos;s created.
              </p>

              <div className="flex justify-end">
                <button type="button" className="btn-primary" onClick={() => goToStep(2)} disabled={!titleValid}>
                  Next: Line items
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Line items</h2>
                <button type="button" className="btn-secondary" onClick={addRow}>
                  + Add line
                </button>
              </div>
              <p className="text-sm text-slate-500">Optional. Leave a row&apos;s description blank to skip it.</p>
              <div className="space-y-4">
                {lineItems.map((li, index) => (
                  <div key={index} className="grid grid-cols-12 gap-3 border-b border-slate-100 pb-4 last:border-0 last:pb-0">
                    <div className="col-span-12 sm:col-span-4">
                      <label className="label">Description</label>
                      <input
                        className={`input-field ${lineItemValidation[index]?.description ? "border-red-300" : ""}`}
                        value={li.description}
                        onChange={(e) => updateLineItem(index, { description: e.target.value })}
                      />
                      {lineItemValidation[index]?.description && <p className="mt-1 text-xs text-red-600">{lineItemValidation[index].description}</p>}
                    </div>
                    <div className="col-span-4 sm:col-span-1">
                      <label className="label">Qty</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        className="input-field"
                        value={li.quantity}
                        onChange={(e) => updateLineItem(index, { quantity: e.target.value })}
                      />
                    </div>
                    <div className="col-span-8 sm:col-span-2">
                      <label className="label">Unit price</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        className={`input-field ${lineItemValidation[index]?.unit_price ? "border-red-300" : ""}`}
                        value={li.unit_price}
                        onChange={(e) => updateLineItem(index, { unit_price: e.target.value })}
                      />
                      {lineItemValidation[index]?.unit_price && <p className="mt-1 text-xs text-red-600">{lineItemValidation[index].unit_price}</p>}
                    </div>
                    <div className="col-span-12 sm:col-span-3">
                      <label className="label">Commodity code</label>
                      <CommodityCodeInput value={li.commodity} onChange={(value) => updateLineItem(index, { commodity: value })} />
                    </div>
                    <div className="col-span-8 sm:col-span-2">
                      <label className="label" title="Classifies this line for spend reporting and GL mapping">Category</label>
                      <CategoryInput
                        id={`line-category-${index}`}
                        value={li.category}
                        placeholder="e.g. IT Hardware"
                        onChange={(value) => updateLineItem(index, { category: value })}
                      />
                      {lineItemValidation[index]?.category && <p className="mt-1 text-xs text-red-600">{lineItemValidation[index].category}</p>}
                    </div>
                    <div className="col-span-4 flex items-end sm:col-span-12 sm:justify-end">
                      <button
                        type="button"
                        className="text-sm text-red-600 hover:underline"
                        onClick={() => removeRow(index)}
                        disabled={lineItems.length === 1}
                      >
                        Remove line
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-between">
                <button type="button" className="btn-secondary" onClick={() => goToStep(1)}>
                  Back
                </button>
                <button type="button" className="btn-primary" onClick={() => goToStep(3)}>
                  Next: Summary
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-6">
              <div className="card space-y-3">
                <h2 className="text-lg font-semibold">Header</h2>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                  <SummaryRow label="Title" value={form.title} />
                  <SummaryRow label="Priority" value={form.priority} />
                  <SummaryRow label="Request type" value={form.request_type} />
                  <SummaryRow label="Estimated value" value={form.estimated_value ? `${form.currency} ${form.estimated_value}` : "—"} />
                  <SummaryRow label="Commodity" value={form.commodity || "—"} />
                  <SummaryRow label="Category" value={form.category || "—"} />
                  <SummaryRow label="Need-by date" value={form.need_by_date || "—"} />
                  <SummaryRow label="Emergency Buy" value={form.is_emergency ? "Yes" : "No"} />
                  <SummaryRow label="Delay until" value={form.delay_until || "—"} />
                  <SummaryRow label="Header tax" value={form.header_tax || "0.00"} />
                  <SummaryRow label="Shipping cost" value={form.shipping_cost || "0.00"} />
                </dl>
                {form.description && (
                  <div>
                    <p className="text-xs font-medium uppercase text-slate-400">Business purpose</p>
                    <p className="text-sm text-slate-700">{form.description}</p>
                  </div>
                )}
                {form.notes && (
                  <div>
                    <p className="text-xs font-medium uppercase text-slate-400">Notes</p>
                    <p className="text-sm text-slate-700">{form.notes}</p>
                  </div>
                )}
              </div>

              <div className="card space-y-3">
                <h2 className="text-lg font-semibold">Line items ({rowsToSubmit.length})</h2>
                {rowsToSubmit.length === 0 ? (
                  <p className="text-sm text-slate-500">No line items added.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                        <th className="py-1 pr-2">Description</th>
                        <th className="py-1 pr-2">Qty</th>
                        <th className="py-1 pr-2">Unit price</th>
                        <th className="py-1 pr-2">Commodity</th>
                        <th className="py-1 text-right">Line total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rowsToSubmit.map((li, i) => (
                        <tr key={i} className="border-b border-slate-100 last:border-0">
                          <td className="py-1 pr-2">{li.description}</td>
                          <td className="py-1 pr-2">{li.quantity}</td>
                          <td className="py-1 pr-2">{li.unit_price || "—"}</td>
                          <td className="py-1 pr-2">{li.commodity || "—"}</td>
                          <td className="py-1 text-right">{lineTotal(li).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <div className="flex justify-end border-t border-slate-200 pt-3">
                  <dl className="w-56 space-y-1 text-sm">
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Lines subtotal</dt>
                      <dd>{linesSubtotal.toFixed(2)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Header tax</dt>
                      <dd>{headerTax.toFixed(2)}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-slate-500">Shipping cost</dt>
                      <dd>{shippingCost.toFixed(2)}</dd>
                    </div>
                    <div className="flex justify-between border-t border-slate-200 pt-1 font-semibold">
                      <dt>Estimated total</dt>
                      <dd>
                        {form.currency} {computedGrandTotal.toFixed(2)}
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>

              <div className="flex justify-between">
                <button type="button" className="btn-secondary" onClick={() => goToStep(2)}>
                  Back
                </button>
                <button type="button" className="btn-primary" disabled={loading} onClick={handleSubmit}>
                  {loading ? "Creating..." : "Create requisition"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800">{value}</dd>
    </div>
  );
}
