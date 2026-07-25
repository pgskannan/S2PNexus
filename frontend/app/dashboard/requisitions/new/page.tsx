"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createRequisition, extractErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setError(null);
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
      router.replace(`/dashboard/requisitions/${requisition.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">New Requisition</h1>
      <form onSubmit={handleSubmit} className="card space-y-4">
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
              Commodity
            </label>
            <input
              id="commodity"
              className="input-field"
              value={form.commodity}
              onChange={(e) => setForm({ ...form, commodity: e.target.value })}
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
        {error && <p className="text-sm text-red-600">{error}</p>}
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
