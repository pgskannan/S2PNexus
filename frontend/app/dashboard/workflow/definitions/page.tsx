"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createWorkflowDefinition, extractErrorMessage, listWorkflowDefinitions } from "@/lib/api";
import type { WorkflowDefinition } from "@/lib/types";

export default function WorkflowDefinitionsPage() {
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [form, setForm] = useState({
    name: "",
    entity_type: "requisition",
    description: "",
    steps: "[]",
    is_active: true,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listWorkflowDefinitions();
      setDefinitions(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const parsedSteps = JSON.parse(form.steps || "[]");
      await createWorkflowDefinition({
        name: form.name,
        entity_type: form.entity_type,
        description: form.description || undefined,
        steps: Array.isArray(parsedSteps) ? parsedSteps : [],
        is_active: form.is_active,
      });
      setForm({ name: "", entity_type: "requisition", description: "", steps: "[]", is_active: true });
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Workflow Definitions</h1>
        <Link href="/dashboard/workflow" className="btn-secondary">
          Back to tasks
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="card overflow-x-auto p-0">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Entity type</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td className="px-4 py-4 text-slate-400" colSpan={3}>
                    Loading...
                  </td>
                </tr>
              )}
              {!loading && definitions.length === 0 && (
                <tr>
                  <td className="px-4 py-4 text-slate-400" colSpan={3}>
                    No workflow definitions yet.
                  </td>
                </tr>
              )}
              {definitions.map((definition) => (
                <tr key={definition.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium">{definition.name}</td>
                  <td className="px-4 py-3">{definition.entity_type}</td>
                  <td className="px-4 py-3">
                    <span className={`badge ${definition.is_active ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-700"}`}>
                      {definition.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4">
          <h2 className="text-lg font-semibold">Create definition</h2>
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
          <div>
            <label className="label" htmlFor="entity_type">
              Entity type
            </label>
            <input
              id="entity_type"
              required
              className="input-field"
              value={form.entity_type}
              onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
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
          <div>
            <label className="label" htmlFor="steps">
              Steps JSON
            </label>
            <textarea
              id="steps"
              className="input-field font-mono text-sm"
              rows={6}
              value={form.steps}
              onChange={(e) => setForm({ ...form, steps: e.target.value })}
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Active
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "Creating..." : "Create definition"}
          </button>
        </form>
      </div>
    </div>
  );
}
