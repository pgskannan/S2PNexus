"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { extractErrorMessage, getWorkflowInstance, getWorkflowDefinition } from "@/lib/api";
import type { WorkflowInstance } from "@/lib/types";
import { ApprovalFlowDiagram, type ApprovalStep } from "@/components/ApprovalFlowDiagram";
import { buildApprovalSteps, resolveApproverNames } from "@/lib/approvalFlow";

export default function WorkflowInstanceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [instance, setInstance] = useState<WorkflowInstance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [approvalSteps, setApprovalSteps] = useState<ApprovalStep[]>([]);

  async function load() {
    try {
      const data = await getWorkflowInstance(params.id);
      setInstance(data);
      if (data.definition_id) {
        const [definition, approverNames] = await Promise.all([
          getWorkflowDefinition(data.definition_id),
          resolveApproverNames(data),
        ]);
        setApprovalSteps(buildApprovalSteps(data, definition.steps, approverNames));
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  if (error && !instance) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!instance) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  return (
    <div className="max-w-6xl space-y-6">
      <button
        onClick={() => router.push("/dashboard/workflow")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to workflow tasks
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold">Workflow instance</h1>
            <p className="mt-1 text-sm text-slate-500">{instance.entity_type}</p>
          </div>
          <span className="badge bg-slate-100 text-slate-700">
            {instance.status}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Current step</dt>
            <dd>{instance.current_step_index}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Entity ID</dt>
            <dd>{instance.entity_id}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Started</dt>
            <dd>{new Date(instance.started_at).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Completed</dt>
            <dd>{instance.completed_at ? new Date(instance.completed_at).toLocaleString() : "—"}</dd>
          </div>
        </dl>

        <div>
          <h2 className="mb-2 font-semibold">Approval flow</h2>
          <ApprovalFlowDiagram
            docNumber={instance.entity_type}
            title={instance.entity_id}
            steps={approvalSteps}
          />
        </div>
      </div>
    </div>
  );
}
