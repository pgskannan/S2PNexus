"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getRequisition,
  transitionRequisition,
  extractErrorMessage,
} from "@/lib/api";
import type { Requisition } from "@/lib/types";

const nextSteps: Record<string, { new_status: string; lifecycle_status: string; label: string }[]> = {
  draft: [
    { new_status: "submitted", lifecycle_status: "submitted", label: "Submit for approval" },
  ],
  submitted: [
    { new_status: "approved", lifecycle_status: "approved", label: "Approve" },
    { new_status: "rejected", lifecycle_status: "rejected", label: "Reject" },
  ],
};

export default function RequisitionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [requisition, setRequisition] = useState<Requisition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const data = await getRequisition(params.id);
      setRequisition(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleTransition(newStatus: string, lifecycleStatus: string) {
    setBusy(true);
    setError(null);
    try {
      const updated = await transitionRequisition(
        params.id,
        newStatus,
        lifecycleStatus
      );
      setRequisition(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error && !requisition) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!requisition) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  const actions = nextSteps[requisition.lifecycle_status] ?? [];

  return (
    <div className="max-w-2xl space-y-6">
      <button
        onClick={() => router.push("/dashboard/requisitions")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to requisitions
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            {requisition.requisition_number && (
              <p className="font-mono text-xs text-slate-400">{requisition.requisition_number}</p>
            )}
            <h1 className="text-xl font-semibold">{requisition.title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {requisition.description || "No description"}
            </p>
          </div>
          <span className="badge bg-slate-100 text-slate-700 capitalize">
            {requisition.lifecycle_status}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Priority</dt>
            <dd className="capitalize">{requisition.priority}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Estimated value</dt>
            <dd>
              {requisition.estimated_value
                ? `${requisition.currency} ${requisition.estimated_value}`
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Commodity</dt>
            <dd>{requisition.commodity || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Category</dt>
            <dd>{requisition.category || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Approval status</dt>
            <dd className="capitalize">{requisition.approval_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Created</dt>
            <dd>{new Date(requisition.created_at).toLocaleString()}</dd>
          </div>
        </dl>

        {error && <p className="text-sm text-red-600">{error}</p>}

        {actions.length > 0 && (
          <div className="flex gap-3 border-t border-slate-100 pt-4">
            {actions.map((action) => (
              <button
                key={action.new_status}
                disabled={busy}
                onClick={() =>
                  handleTransition(action.new_status, action.lifecycle_status)
                }
                className="btn-primary"
              >
                {action.label}
              </button>
            ))}
          </div>
        )}
        {actions.length === 0 && (
          <p className="border-t border-slate-100 pt-4 text-sm text-slate-400">
            No further transitions available from this status.
          </p>
        )}
      </div>
    </div>
  );
}
