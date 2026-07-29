"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { extractErrorMessage, getWorkflowInstance, getWorkflowDefinition } from "@/lib/api";
import type { WorkflowInstance } from "@/lib/types";
import { WorkflowCanvas } from "@/components/WorkflowCanvas";

export default function WorkflowInstanceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [instance, setInstance] = useState<WorkflowInstance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [definitionSteps, setDefinitionSteps] = useState<Array<Record<string, unknown>>>([]);

  async function load() {
    try {
      const data = await getWorkflowInstance(params.id);
      setInstance(data);
      if (data.definition_id) {
        const definition = await getWorkflowDefinition(data.definition_id);
        setDefinitionSteps(definition.steps as Array<Record<string, unknown>>);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const highlightedNodeId = useMemo(() => {
    if (!instance) {
      return null;
    }
    return instance.current_step_index >= 0 && instance.current_step_index < definitionSteps.length
      ? `step-${instance.current_step_index}`
      : null;
  }, [definitionSteps.length, instance]);

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

        <div className="rounded-lg border border-slate-200 p-4">
          <h2 className="font-semibold">Flow</h2>
          <div className="mt-3 h-[420px]">
            <WorkflowCanvas value={definitionSteps} onChange={() => undefined} highlightedNodeId={highlightedNodeId} />
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-4">
          <h2 className="font-semibold">Tasks</h2>
          {instance.tasks.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No tasks yet.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {instance.tasks.map((task) => (
                <li key={task.id} className="rounded bg-slate-50 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <span>{task.step_name}</span>
                    <span className="text-slate-500">{task.status}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
