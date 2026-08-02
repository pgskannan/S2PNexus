"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  completeWorkflowTask,
  getDashboardMetrics,
  getSavingsSummary,
  listMyWorkflowTasks,
  listRequisitions,
  listSourcingEvents,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { DashboardMetricsResponse, WorkflowTask } from "@/lib/types";

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function formatCurrency(value: number | string | null | undefined) {
  const numericValue = typeof value === "number" ? value : Number.parseFloat(`${value ?? 0}`);
  return Number.isFinite(numericValue) ? currencyFormatter.format(numericValue) : "$0";
}

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const [metrics, setMetrics] = useState<DashboardMetricsResponse | null>(null);
  const [reqTotal, setReqTotal] = useState<number | null>(null);
  const [sourcingTotal, setSourcingTotal] = useState<number | null>(null);
  const [myApprovals, setMyApprovals] = useState<WorkflowTask[]>([]);
  const [approvalsBusyId, setApprovalsBusyId] = useState<string | null>(null);
  const [savingsSummary, setSavingsSummary] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      const [metricsResult, requisitionsResult, sourcingResult, tasksResult, savingsResult] = await Promise.allSettled([
        getDashboardMetrics(),
        listRequisitions(),
        listSourcingEvents(),
        listMyWorkflowTasks({ status: "pending" }),
        getSavingsSummary(),
      ]);

      if (!mounted) return;

      if (metricsResult.status === "fulfilled") {
        setMetrics(metricsResult.value);
      }
      if (requisitionsResult.status === "fulfilled") {
        setReqTotal(requisitionsResult.value.total);
      } else {
        setReqTotal(0);
      }
      if (sourcingResult.status === "fulfilled") {
        setSourcingTotal(sourcingResult.value.total);
      } else {
        setSourcingTotal(0);
      }
      if (tasksResult.status === "fulfilled") {
        setMyApprovals(tasksResult.value);
      } else {
        setMyApprovals([]);
      }
      if (savingsResult.status === "fulfilled") {
        setSavingsSummary(savingsResult.value.total_savings);
      } else {
        setSavingsSummary("0");
      }
    };

    load();
    return () => {
      mounted = false;
    };
  }, []);

  async function handleApproval(taskId: string, decision: "approve" | "reject") {
    setApprovalsBusyId(taskId);
    try {
      await completeWorkflowTask(taskId, { decision });
      setMyApprovals((current) => current.filter((task) => task.id !== taskId));
    } finally {
      setApprovalsBusyId(null);
    }
  }

  const monthlySpend = metrics?.spend_by_month.slice(-6) ?? [];
  const maxMonthlySpend = Math.max(1, ...monthlySpend.map((item) => Number(item.amount || 0)));
  const topCategories = metrics?.spend_by_category.slice(0, 4) ?? [];
  const topSuppliers = metrics?.top_suppliers.slice(0, 3) ?? [];
  const pendingTasks = myApprovals.length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">
          Welcome back{user ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Here&apos;s what&apos;s happening across your S2P operations.
        </p>
      </div>

      <div className="card border-amber-200 bg-amber-50/40">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-amber-700">My Approvals</p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900">
              {pendingTasks === 0 ? "You are caught up" : `${pendingTasks} waiting on you`}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Approve or reject assigned workflow tasks without leaving the dashboard.
            </p>
          </div>
          <Link href="/dashboard/workflow" className="btn-secondary">
            Open My Approvals
          </Link>
        </div>
        <div className="mt-4 space-y-2">
          {myApprovals.length === 0 ? (
            <p className="rounded-lg border border-dashed border-amber-200 bg-white px-3 py-4 text-sm text-slate-500">
              No pending approvals right now.
            </p>
          ) : (
            myApprovals.slice(0, 5).map((task) => (
              <div
                key={task.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5"
              >
                <div className="min-w-0">
                  <Link
                    href={`/dashboard/workflow/instances/${task.instance_id}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {task.step_name}
                  </Link>
                  {task.reason && <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{task.reason}</p>}
                  <p className="mt-0.5 text-xs text-slate-400">
                    Due {task.due_at ? new Date(task.due_at).toLocaleDateString() : "—"}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    disabled={approvalsBusyId === task.id}
                    onClick={() => handleApproval(task.id, "approve")}
                    className="btn-primary"
                  >
                    Approve
                  </button>
                  <button
                    disabled={approvalsBusyId === task.id}
                    onClick={() => handleApproval(task.id, "reject")}
                    className="btn-secondary"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="card">
          <p className="text-sm text-slate-500">Total spend</p>
          <p className="mt-2 text-3xl font-semibold">
            {metrics ? formatCurrency(metrics.total_spend) : "..."}
          </p>
          <p className="mt-2 text-sm text-slate-500">
            Across {metrics?.total_contracts ?? "..."} contracts and active supplier relationships.
          </p>
        </div>
        <div className="card">
          <p className="text-sm text-slate-500">Pending approvals</p>
          <p className="mt-2 text-3xl font-semibold">
            {metrics ? metrics.pending_approvals : pendingTasks}
          </p>
          <Link href="/dashboard/workflow" className="mt-3 inline-block text-sm text-brand-600 hover:underline">
            Review My Approvals
          </Link>
        </div>
        <div className="card">
          <p className="text-sm text-slate-500">Savings captured</p>
          <p className="mt-2 text-3xl font-semibold">
            {savingsSummary ? formatCurrency(savingsSummary) : "..."}
          </p>
          <Link href="/dashboard/spend" className="mt-3 inline-block text-sm text-brand-600 hover:underline">
            Open spend dashboard
          </Link>
        </div>
        <div className="card">
          <p className="text-sm text-slate-500">AI Agent</p>
          <p className="mt-2 text-sm text-slate-600">
            Ask the orchestrator to look up or act on procurement, supplier, contract, sourcing, or spend data.
          </p>
          <Link href="/dashboard/agent" className="mt-3 inline-block text-sm text-brand-600 hover:underline">
            Try it
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Spend trend</p>
              <p className="mt-1 text-lg font-semibold">Latest monthly activity</p>
            </div>
            <Link href="/dashboard/spend" className="text-sm text-brand-600 hover:underline">
              View analytics
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {monthlySpend.length > 0 ? monthlySpend.map((item) => {
              const amount = Number(item.amount || 0);
              const width = Math.max(10, (amount / maxMonthlySpend) * 100);
              return (
                <div key={item.month} className="flex items-center gap-3 text-sm">
                  <span className="w-14 text-slate-500">{item.month.slice(5)}</span>
                  <div className="h-2 flex-1 rounded-full bg-slate-200">
                    <div className="h-2 rounded-full bg-brand-600" style={{ width: `${width}%` }} />
                  </div>
                  <span className="w-24 text-right text-slate-700">{formatCurrency(amount)}</span>
                </div>
              );
            }) : <p className="text-sm text-slate-500">No spend history yet.</p>}
          </div>
        </div>

        <div className="card">
          <p className="text-sm text-slate-500">Key areas</p>
          <div className="mt-4 space-y-3">
            <Link href="/dashboard/requisitions" className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 hover:border-brand-300">
              <span className="text-sm font-medium text-slate-700">Requisitions</span>
              <span className="text-sm text-slate-500">{reqTotal ?? "..."}</span>
            </Link>
            <Link href="/dashboard/contracts" className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 hover:border-brand-300">
              <span className="text-sm font-medium text-slate-700">Contracts</span>
              <span className="text-sm text-slate-500">{metrics?.total_contracts ?? "..."}</span>
            </Link>
            <Link href="/dashboard/sourcing" className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 hover:border-brand-300">
              <span className="text-sm font-medium text-slate-700">Sourcing</span>
              <span className="text-sm text-slate-500">{sourcingTotal ?? "..."}</span>
            </Link>
            <Link href="/dashboard/suppliers" className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 hover:border-brand-300">
              <span className="text-sm font-medium text-slate-700">Suppliers</span>
              <span className="text-sm text-slate-500">{metrics?.total_suppliers ?? "..."}</span>
            </Link>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Top categories</p>
              <p className="mt-1 text-lg font-semibold">Spend mix</p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {topCategories.length > 0 ? topCategories.map((item) => (
              <div key={item.category} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-700">{item.category}</span>
                  <span className="text-slate-500">{item.percentage.toFixed(1)}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-200">
                  <div className="h-2 rounded-full bg-slate-400" style={{ width: `${Math.max(8, item.percentage)}%` }} />
                </div>
              </div>
            )) : <p className="text-sm text-slate-500">No category data yet.</p>}
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-500">Top suppliers</p>
              <p className="mt-1 text-lg font-semibold">Most spend</p>
            </div>
          </div>
          <div className="mt-4 space-y-3">
            {topSuppliers.length > 0 ? topSuppliers.map((supplier) => (
              <div key={supplier.supplier_id} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-slate-700">{supplier.supplier_name}</p>
                  <p className="text-xs text-slate-500">{supplier.contract_count} contract{supplier.contract_count === 1 ? "" : "s"}</p>
                </div>
                <p className="text-sm text-slate-700">{formatCurrency(supplier.total_spend)}</p>
              </div>
            )) : <p className="text-sm text-slate-500">No supplier data yet.</p>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Link href="/dashboard/requisitions/new" className="card hover:border-brand-300">
          <p className="font-medium text-brand-700">+ New Requisition</p>
          <p className="mt-1 text-sm text-slate-500">
            Start a purchase requisition for a business need.
          </p>
        </Link>
        <Link href="/dashboard/suppliers/new" className="card hover:border-brand-300">
          <p className="font-medium text-brand-700">+ New Supplier</p>
          <p className="mt-1 text-sm text-slate-500">
            Add a supplier to your vendor master.
          </p>
        </Link>
      </div>
    </div>
  );
}
