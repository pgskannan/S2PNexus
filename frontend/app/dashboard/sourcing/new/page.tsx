"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createSourcingEvent, extractErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export default function NewSourcingPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const [form, setForm] = useState({
    event_number: "",
    title: "",
    description: "",
    event_type: "rfp",
    category: "",
    currency: "USD",
    estimated_value: "",
    start_date: "",
    response_due_date: "",
    status: "draft",
    lifecycle_status: "draft",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setError(null);
    setLoading(true);
    try {
      const event = await createSourcingEvent({
        event_number: form.event_number,
        title: form.title,
        description: form.description || undefined,
        event_type: form.event_type,
        category: form.category || undefined,
        owner_id: user.id,
        currency: form.currency,
        estimated_value: form.estimated_value || undefined,
        start_date: form.start_date || undefined,
        response_due_date: form.response_due_date || undefined,
        status: form.status,
        lifecycle_status: form.lifecycle_status,
      });
      router.replace(`/dashboard/sourcing/${event.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">New Sourcing Event</h1>
      <form onSubmit={handleSubmit} className="card space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="event_number">
              Event number
            </label>
            <input
              id="event_number"
              required
              className="input-field"
              value={form.event_number}
              onChange={(e) => setForm({ ...form, event_number: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="event_type">
              Event type
            </label>
            <select
              id="event_type"
              className="input-field"
              value={form.event_type}
              onChange={(e) => setForm({ ...form, event_type: e.target.value })}
            >
              <option value="rfi">RFI</option>
              <option value="rfp">RFP</option>
              <option value="rfq">RFQ</option>
              <option value="auction">Auction</option>
            </select>
          </div>
        </div>
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
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
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
              onChange={(e) => setForm({ ...form, estimated_value: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="response_due_date">
              Response due date
            </label>
            <input
              id="response_due_date"
              type="date"
              className="input-field"
              value={form.response_due_date}
              onChange={(e) => setForm({ ...form, response_due_date: e.target.value })}
            />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-3">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? "Creating..." : "Create sourcing event"}
          </button>
          <button type="button" className="btn-secondary" onClick={() => router.back()}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
