"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createContract, extractErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export default function NewContractPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  const [form, setForm] = useState({
    title: "",
    contract_number: "",
    supplier_id: "",
    contract_type: "master",
    description: "",
    start_date: "",
    end_date: "",
    value: "",
    currency: "USD",
    terms_and_conditions: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setError(null);
    setLoading(true);
    try {
      const contract = await createContract({
        title: form.title,
        contract_number: form.contract_number,
        supplier_id: form.supplier_id,
        contract_type: form.contract_type,
        description: form.description || undefined,
        start_date: form.start_date,
        end_date: form.end_date || undefined,
        value: form.value ? form.value : undefined,
        currency: form.currency,
        terms_and_conditions: form.terms_and_conditions || undefined,
      });
      router.replace(`/dashboard/contracts/${contract.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">New Contract</h1>
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
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="contract_number">
              Contract number
            </label>
            <input
              id="contract_number"
              required
              className="input-field"
              value={form.contract_number}
              onChange={(e) => setForm({ ...form, contract_number: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="contract_type">
              Contract type
            </label>
            <select
              id="contract_type"
              className="input-field"
              value={form.contract_type}
              onChange={(e) => setForm({ ...form, contract_type: e.target.value })}
            >
              <option value="master">Master</option>
              <option value="statement_of_work">Statement of Work</option>
              <option value="services">Services</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label" htmlFor="supplier_id">
            Supplier ID
          </label>
          <input
            id="supplier_id"
            required
            className="input-field"
            value={form.supplier_id}
            onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="start_date">
              Start date
            </label>
            <input
              id="start_date"
              required
              type="date"
              className="input-field"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="end_date">
              End date
            </label>
            <input
              id="end_date"
              type="date"
              className="input-field"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="value">
              Value
            </label>
            <input
              id="value"
              type="number"
              min="0"
              step="0.01"
              className="input-field"
              value={form.value}
              onChange={(e) => setForm({ ...form, value: e.target.value })}
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
        <div>
          <label className="label" htmlFor="terms_and_conditions">
            Terms and conditions
          </label>
          <textarea
            id="terms_and_conditions"
            className="input-field"
            rows={3}
            value={form.terms_and_conditions}
            onChange={(e) => setForm({ ...form, terms_and_conditions: e.target.value })}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex gap-3">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? "Creating..." : "Create contract"}
          </button>
          <button type="button" className="btn-secondary" onClick={() => router.back()}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
