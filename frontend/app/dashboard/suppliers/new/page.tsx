"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createSupplier, extractErrorMessage } from "@/lib/api";

export default function NewSupplierPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    contact_email: "",
    contact_phone: "",
    address: "",
    website: "",
    payment_terms: "",
    currency: "USD",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await createSupplier({
        name: form.name,
        contact_email: form.contact_email || undefined,
        contact_phone: form.contact_phone || undefined,
        address: form.address || undefined,
        website: form.website || undefined,
        payment_terms: form.payment_terms || undefined,
        currency: form.currency,
      });
      router.replace("/dashboard/suppliers");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">New Supplier</h1>
      <form onSubmit={handleSubmit} className="card space-y-4">
        <div>
          <label className="label" htmlFor="name">
            Name
          </label>
          <input
            id="name"
            required
            className="input-field"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="contact_email">
              Contact email
            </label>
            <input
              id="contact_email"
              type="email"
              className="input-field"
              value={form.contact_email}
              onChange={(e) =>
                setForm({ ...form, contact_email: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label" htmlFor="contact_phone">
              Contact phone
            </label>
            <input
              id="contact_phone"
              className="input-field"
              value={form.contact_phone}
              onChange={(e) =>
                setForm({ ...form, contact_phone: e.target.value })
              }
            />
          </div>
        </div>
        <div>
          <label className="label" htmlFor="address">
            Address
          </label>
          <input
            id="address"
            className="input-field"
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="website">
              Website
            </label>
            <input
              id="website"
              className="input-field"
              value={form.website}
              onChange={(e) => setForm({ ...form, website: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="payment_terms">
              Payment terms
            </label>
            <input
              id="payment_terms"
              placeholder="Net 30"
              className="input-field"
              value={form.payment_terms}
              onChange={(e) =>
                setForm({ ...form, payment_terms: e.target.value })
              }
            />
          </div>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-3">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? "Creating..." : "Create supplier"}
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
