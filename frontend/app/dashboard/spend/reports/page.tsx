"use client";

import { Fragment, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  extractErrorMessage,
  getApprovalBottlenecks,
  getExceptionDashboard,
  getPoAging,
  getSupplierScorecard,
  retryExceptionRequisition,
} from "@/lib/api";
import type {
  ApprovalBottleneckResponse,
  ExceptionDashboardResponse,
  ExceptionRequisition,
  ExceptionRetryResponse,
  PoAgingResponse,
  SupplierScorecardResponse,
} from "@/lib/types";

type Tab = "scorecard" | "po-aging" | "approval-bottlenecks" | "exceptions";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "scorecard", label: "Supplier Scorecard" },
  { id: "po-aging", label: "PO Aging" },
  { id: "approval-bottlenecks", label: "Approval Bottlenecks" },
  { id: "exceptions", label: "Exceptions" },
];

function currency(value: string | number | undefined | null, cur = "USD"): string {
  const n = Number(value) || 0;
  return n.toLocaleString("en-US", { style: "currency", currency: cur || "USD" });
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h3 className="mb-3 font-semibold text-slate-900">{title}</h3>
      {children}
    </div>
  );
}

function ErrorBanner({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  if (!error) return null;
  return (
    <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3">
      <p className="text-sm text-red-700">{error}</p>
      <button onClick={onRetry} className="text-sm font-medium text-red-700 underline">
        Retry
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1. Supplier performance scorecard
// ---------------------------------------------------------------------------
function SupplierScorecardView() {
  const [data, setData] = useState<SupplierScorecardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    getSupplierScorecard()
      .then(setData)
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  if (loading) return <p className="text-sm text-slate-400">Loading…</p>;
  if (error) return <ErrorBanner error={error} onRetry={load} />;
  if (!data || data.items.length === 0) {
    return <p className="text-sm text-slate-500">No suppliers to score yet.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Supplier</th>
            <th className="px-4 py-3">POs</th>
            <th className="px-4 py-3">Open POs</th>
            <th className="px-4 py-3">PO value</th>
            <th className="px-4 py-3">Receipts</th>
            <th className="px-4 py-3">Exceptions</th>
            <th className="px-4 py-3">Exception rate</th>
            <th className="px-4 py-3">Spend</th>
            <th className="px-4 py-3">Risk</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.items.map((s) => (
            <tr key={s.supplier_id} className="hover:bg-slate-50">
              <td className="px-4 py-3 font-medium text-slate-900">{s.supplier_name}</td>
              <td className="px-4 py-3">{s.total_purchase_orders}</td>
              <td className="px-4 py-3">{s.open_purchase_orders}</td>
              <td className="px-4 py-3">{currency(s.po_value)}</td>
              <td className="px-4 py-3">{s.receipt_count}</td>
              <td className="px-4 py-3">{s.exception_receipt_count}</td>
              <td className="px-4 py-3">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    s.exception_rate > 0 ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"
                  }`}
                >
                  {s.exception_rate}%
                </span>
              </td>
              <td className="px-4 py-3">{currency(s.total_spend)}</td>
              <td className="px-4 py-3 capitalize">{s.risk_level ?? "—"}</td>
              <td className="px-4 py-3 capitalize">{s.lifecycle_status ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. PO aging
// ---------------------------------------------------------------------------
function PoAgingView() {
  const [data, setData] = useState<PoAgingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    getPoAging()
      .then(setData)
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  if (loading) return <p className="text-sm text-slate-400">Loading…</p>;
  if (error) return <ErrorBanner error={error} onRetry={load} />;
  if (!data || data.buckets.length === 0) {
    return <p className="text-sm text-slate-500">No open purchase orders.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Open POs">
          <p className="text-3xl font-semibold">{data.total_count}</p>
        </Card>
        <Card title="Open PO value">
          <p className="text-3xl font-semibold">{currency(data.total_value)}</p>
        </Card>
        <Card title="As of">
          <p className="text-3xl font-semibold">{data.as_of}</p>
        </Card>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Age bucket</th>
              <th className="px-4 py-3">Lifecycle status</th>
              <th className="px-4 py-3">Count</th>
              <th className="px-4 py-3">Value</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.buckets.map((b) => (
              <tr key={`${b.bucket}-${b.lifecycle_status}`} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                    {b.bucket} days
                  </span>
                </td>
                <td className="px-4 py-3 capitalize">{b.lifecycle_status}</td>
                <td className="px-4 py-3">{b.count}</td>
                <td className="px-4 py-3">{currency(b.total_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. Approval bottlenecks
// ---------------------------------------------------------------------------
function ApprovalBottlenecksView() {
  const [data, setData] = useState<ApprovalBottleneckResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    getApprovalBottlenecks()
      .then(setData)
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  if (loading) return <p className="text-sm text-slate-400">Loading…</p>;
  if (error) return <ErrorBanner error={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Card title="Pending approvals">
          <p className="text-3xl font-semibold">{data.pending_tasks}</p>
        </Card>
        <Card title="Blocked approvals">
          <p className="text-3xl font-semibold">{data.blocked_tasks}</p>
        </Card>
        <Card title="Overdue pending">
          <p className="text-3xl font-semibold">{data.overdue_pending}</p>
        </Card>
        <Card title="Avg pending age (days)">
          <p className="text-3xl font-semibold">{data.avg_pending_age_days}</p>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Oldest open approvals">
          {data.oldest_pending.length === 0 ? (
            <p className="text-sm text-slate-500">No open approval tasks.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.oldest_pending.map((t) => (
                <li key={t.task_id} className="flex items-center justify-between rounded bg-slate-50 px-3 py-2">
                  <div>
                    <p className="font-medium text-slate-800">{t.step_name}</p>
                    <p className="text-xs text-slate-500">
                      {t.entity_type} · {t.age_days} days old{t.due_at ? ` · due ${t.due_at.slice(0, 10)}` : ""}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      t.status === "blocked" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                    }`}
                  >
                    {t.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Slowest approval nodes">
          {data.slowest_nodes.length === 0 ? (
            <p className="text-sm text-slate-500">No completed approvals to measure yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.slowest_nodes
                .slice()
                .sort((a, b) => b.avg_approval_hours - a.avg_approval_hours)
                .map((n) => (
                  <li key={n.node} className="flex items-center justify-between rounded bg-slate-50 px-3 py-2">
                    <span className="font-medium text-slate-800">{n.node}</span>
                    <span className="text-slate-600">
                      {n.avg_approval_hours} hrs · {n.count} approvals
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4. Exception dashboard
// ---------------------------------------------------------------------------
function ExceptionDashboardView() {
  const [data, setData] = useState<ExceptionDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryMsg, setRetryMsg] = useState<Record<string, string>>({});
  const router = useRouter();

  function load() {
    setLoading(true);
    setError(null);
    getExceptionDashboard()
      .then(setData)
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function handleRetry(req: ExceptionRequisition) {
    setRetrying(req.requisition_id);
    setRetryMsg((m) => ({ ...m, [req.requisition_id]: "" }));
    try {
      const res: ExceptionRetryResponse = await retryExceptionRequisition(req.requisition_id);
      setRetryMsg((m) => ({
        ...m,
        [req.requisition_id]: res.ok
          ? `✅ ${res.message}`
          : `⚠️ ${res.message}`,
      }));
      if (res.ok) {
        // Refresh after a successful retry so the resolved PR drops off.
        getExceptionDashboard()
          .then(setData)
          .catch(() => undefined);
      }
    } catch (e) {
      setRetryMsg((m) => ({ ...m, [req.requisition_id]: extractErrorMessage(e) }));
    } finally {
      setRetrying(null);
    }
  }

  if (loading) return <p className="text-sm text-slate-400">Loading…</p>;
  if (error) return <ErrorBanner error={error} onRetry={load} />;
  if (!data || data.items.length === 0) {
    return <p className="text-sm text-slate-500">No exception requisitions. 🎉</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        Requisitions where PO auto-creation was blocked at approval. Fix the underlying issue (e.g. supplier
        email, inactive supplier, missing GL code) and retry.
      </p>
      <div className="space-y-3">
        {data.items.map((req) => (
          <div key={req.requisition_id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-900">
                  {req.title}{" "}
                  {req.requisition_number && (
                    <span className="font-mono text-xs font-normal text-slate-400">{req.requisition_number}</span>
                  )}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {req.supplier_name ?? "No supplier"} · {currency(req.estimated_value, req.currency)} · updated{" "}
                  {req.updated_at ? new Date(req.updated_at).toLocaleDateString() : "—"}
                </p>
              </div>
              <button
                onClick={() => handleRetry(req)}
                disabled={retrying === req.requisition_id}
                className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {retrying === req.requisition_id ? "Retrying…" : "Resolve & retry"}
              </button>
            </div>
            {req.reasons.length > 0 && (
              <ul className="mt-3 space-y-1">
                {req.reasons.map((reason, i) => (
                  <li key={i} className="rounded bg-red-50 px-3 py-1.5 text-xs text-red-700">
                    {reason}
                  </li>
                ))}
              </ul>
            )}
            {retryMsg[req.requisition_id] && (
              <p className="mt-2 text-xs text-slate-600">{retryMsg[req.requisition_id]}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ReportsPage() {
  const [tab, setTab] = useState<Tab>("scorecard");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Reports & Analytics</h1>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-md px-3 py-2 text-sm font-medium ${
              tab === t.id
                ? "bg-brand-600 text-white"
                : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div>
        {tab === "scorecard" && <SupplierScorecardView />}
        {tab === "po-aging" && <PoAgingView />}
        {tab === "approval-bottlenecks" && <ApprovalBottlenecksView />}
        {tab === "exceptions" && <ExceptionDashboardView />}
      </div>
    </div>
  );
}
