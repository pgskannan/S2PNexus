"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createRequisition, addRequisitionLineItem, extractErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import CommodityCodeInput from "@/components/CommodityCodeInput";

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

export default function NewRequisitionPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const [form, setForm] = useState({
    title: "",
    description: "",
    request_type: "catalog",
    currency: "USD",
    estimated_value: "",
    priority: "medium",
    commodity: "",
    category: "",
    notes: "",
  });
  const [lineItems, setLineItems] = useState<LineItemDraft[]>([emptyLineItem()]);
  const [error, setError] = useState<string | null>(null);
  const [lineItemWarning, setLineItemWarning] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function updateLineItem(index: number, patch: Partial<LineItemDraft>) {
    setLineItems((items) =>
      items.map((item, i) => (i === index ? { ...item, ...patch } : item))
    );
  }

  function addRow() {
    setLineItems((items) => [...items, emptyLineItem()]);
  }

  function removeRow(index: number) {
    setLineItems((items) => items.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setError(null);
    setLineItemWarning(null);
    setLoading(true);
    try {
      const requisition = await createRequisition({
        title: form.title,
        description: form.description || undefined,
        request_type: form.request_type,
        currency: form.currency,
        estimated_value: form.estimated_value
          ? form.estimated_value
          : undefined,
        priority: form.priority,
        commodity: form.commodity || undefined,
        category: form.category || undefined,
        notes: form.notes || undefined,
        requested_by: user.id,
      });

      // Line items are added one at a time against the already-created
      // requisition (there's no combined create-with-line-items endpoint for
      // requisitions, unlike purchase orders). Skip fully-blank rows -- the
      // first row starts empty so a plain header-only requisition still works.
      const rowsToSubmit = lineItems.filter((li) => li.description.trim());
      let failedCount = 0;
      for (const li of rowsToSubmit) {
        const quantity = li.quantity ? Number(li.quantity) : 1;
        const unitPrice = li.unit_price ? Number(li.unit_price) : undefined;
        const lineTotal =
          unitPrice !== undefined ? (quantity * unitPrice).toFixed(2) : undefined;
        try {
          await addRequisitionLineItem(requisition.id, {
            description: li.description,
            quantity: li.quantity || "1",
            unit_price: li.unit_price || undefined,
            line_total: lineTotal,
            commodity: li.commodity || undefined,
            category: li.category || undefined,
            account_code: li.account_code || undefined,
          });
        } catch {
          failedCount += 1;
        }
      }
      if (failedCount > 0) {
        // The requisition itself was created successfully -- don't block
        // navigation on a partial line-item failure, just surface it. The
        // user can retry adding the missing line(s) from the detail page.
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
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">New Requisition</h1>
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="card space-y-4">
          <div>
            <label className="label" htmlFor="title">
              Title
            </label>
            <input
              id="title"
              required
              className="input-field"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="description">
              Description
            </label>
            <textarea
              id="description"
              className="input-field"
              rows={3}
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
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
                onChange={(e) =>
                  setForm({ ...form, request_type: e.target.value })
                }
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
                className="input-field"
                value={form.estimated_value}
                onChange={(e) =>
                  setForm({ ...form, estimated_value: e.target.value })
                }
              />
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
                onChange={(e) =>
                  setForm({ ...form, currency: e.target.value.toUpperCase() })
                }
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
              <label className="label" htmlFor="category">
                Category
              </label>
              <input
                id="category"
                className="input-field"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
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
            <button type="button" className="btn-secondary" onClick={addRow}>
              + Add line
            </button>
          </div>
          <p className="text-sm text-slate-500">
            Optional. Leave a row&apos;s description blank to skip it.
          </p>
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
                    onChange={(e) =>
                      updateLineItem(index, { description: e.target.value })
                    }
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
                    onChange={(e) =>
                      updateLineItem(index, { quantity: e.target.value })
                    }
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
                    onChange={(e) =>
                      updateLineItem(index, { unit_price: e.target.value })
                    }
                  />
                </div>
                <div className="col-span-12 sm:col-span-3">
                  <label className="label">Commodity code</label>
                  <CommodityCodeInput
                    value={li.commodity}
                    onChange={(value) => updateLineItem(index, { commodity: value })}
                  />
                </div>
                <div className="col-span-8 sm:col-span-2">
                  <label className="label">Category</label>
                  <input
                    className="input-field"
                    value={li.category}
                    onChange={(e) =>
                      updateLineItem(index, { category: e.target.value })
                    }
                  />
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
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {lineItemWarning && (
          <p className="text-sm text-amber-600">{lineItemWarning}</p>
        )}
        <div className="flex gap-3">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? "Creating..." : "Create requisition"}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => router.back()}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
