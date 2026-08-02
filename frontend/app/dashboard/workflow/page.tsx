"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { completeWorkflowTask, extractErrorMessage, listMyWorkflowTasks } from "@/lib/api";
import type { WorkflowTask } from "@/lib/types";

const statusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  completed: "bg-green-100 text-green-700",
};

export default function WorkflowPage() {
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listMyWorkflowTasks({ status: "pending" });
      setTasks(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleComplete(taskId: string, decision: "approve" | "reject") {
    setBusyId(taskId);
    setError(null);
    try {
      await completeWorkflowTask(taskId, { decision });
      setTasks((current) => current.filter((task) => task.id !== taskId));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">My Approvals</h1>
          <p className="mt-1 text-sm text-slate-500">Tasks assigned to you across requisitions and other workflows.</p>
        </div>
        <Link href="/dashboard/workflow/definitions" className="btn-secondary">
          Workflow rules
        </Link>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Step</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Due</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={4}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && tasks.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={4}>
                  No pending approvals.
                </td>
              </tr>
            )}
            {tasks.map((task) => (
              <tr key={task.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/dashboard/workflow/instances/${task.instance_id}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {task.step_name}
                  </Link>
                  {task.reason && (
                    <p className="mt-0.5 max-w-md text-xs text-slate-500">
                      <span className="font-medium text-slate-600">Why:</span> {task.reason}
                    </p>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={`badge ${statusColors[task.status] ?? "bg-slate-100 text-slate-700"}`}>
                    {task.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500">
                  {task.due_at ? new Date(task.due_at).toLocaleDateString() : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      disabled={busyId === task.id}
                      onClick={() => handleComplete(task.id, "approve")}
                      className="btn-primary"
                    >
                      {busyId === task.id ? "Working..." : "Approve"}
                    </button>
                    <button
                      disabled={busyId === task.id}
                      onClick={() => handleComplete(task.id, "reject")}
                      className="btn-secondary"
                    >
                      Reject
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
