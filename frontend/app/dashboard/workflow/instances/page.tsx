"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { extractErrorMessage, listWorkflowInstances } from "@/lib/api";
import type { WorkflowInstance } from "@/lib/types";

const PAGE_SIZE = 25;

const ENTITY_TYPES = [
  "requisition",
  "purchase_order",
  "contract",
  "sourcing_event",
  "goods_receipt",
  "invoice_approval",
  "invoice_exception",
  "supplier",
];

const STATUSES = ["in_progress", "completed", "rejected", "blocked"];

const statusColors: Record<string, string> = {
  in_progress: "bg-amber-100 text-amber-700",
  completed: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  blocked: "bg-orange-100 text-orange-700",
};

export default function WorkflowInstancesPage() {
  const [instances, setInstances] = useState<WorkflowInstance[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [entityType, setEntityType] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkflowInstances({
        entity_type: entityType || undefined,
        status: status || undefined,
        skip,
        limit: PAGE_SIZE,
      });
      setInstances(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, status, skip]);

  const rangeStart = total === 0 ? 0 : skip + 1;
  const rangeEnd = Math.min(skip + PAGE_SIZE, total);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Workflow instances</h1>
          <p className="mt-1 text-sm text-slate-500">
            Active and historical approval queues across every document type.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/dashboard/workflow" className="btn-secondary">
            My Tasks
          </Link>
          <Link href="/dashboard/workflow/definitions" className="btn-secondary">
            Manage Definitions
          </Link>
        </div>
      </div>

      <div className="card flex flex-wrap items-end gap-4 p-4">
        <div>
          <label className="label" htmlFor="entity_type_filter">
            Document type
          </label>
          <select
            id="entity_type_filter"
            className="input-field"
            value={entityType}
            onChange={(e) => {
              setSkip(0);
              setEntityType(e.target.value);
            }}
          >
            <option value="">All types</option>
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="status_filter">
            Status
          </label>
          <select
            id="status_filter"
            className="input-field"
            value={status}
            onChange={(e) => {
              setSkip(0);
              setStatus(e.target.value);
            }}
          >
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Document type</th>
              <th className="px-4 py-3">Entity ID</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Current step</th>
              <th className="px-4 py-3">Started</th>
              <th className="px-4 py-3">Completed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && instances.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={6}>
                  No workflow instances match these filters.
                </td>
              </tr>
            )}
            {!loading &&
              instances.map((instance) => (
                <tr key={instance.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link
                      href={`/dashboard/workflow/instances/${instance.id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {instance.entity_type}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{instance.entity_id}</td>
                  <td className="px-4 py-3">
                    <span className={`badge ${statusColors[instance.status] ?? "bg-slate-100 text-slate-700"}`}>
                      {instance.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{instance.current_step_index}</td>
                  <td className="px-4 py-3 text-slate-500">{new Date(instance.started_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {instance.completed_at ? new Date(instance.completed_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {total > 0 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            Showing {rangeStart}-{rangeEnd} of {total}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondary"
              disabled={skip === 0 || loading}
              onClick={() => setSkip((current) => Math.max(0, current - PAGE_SIZE))}
            >
              Previous
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={skip + PAGE_SIZE >= total || loading}
              onClick={() => setSkip((current) => current + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
