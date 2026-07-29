"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createWorkflowDefinition, extractErrorMessage, listWorkflowDefinitions } from "@/lib/api";
import type { WorkflowDefinition } from "@/lib/types";
import { WorkflowCanvas, type WorkflowStepValue } from "@/components/WorkflowCanvas";
import { WorkflowNodeInspector } from "@/components/WorkflowNodeInspector";

export default function WorkflowDefinitionsPage() {
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [form, setForm] = useState({
    name: "",
    entity_type: "requisition",
    description: "",
    steps: [] as Array<Record<string, unknown>>,
    is_active: true,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);

  const selectedNode = useMemo(() => {
    const index = form.steps.findIndex((step, stepIndex) => `step-${stepIndex}` === selectedNodeId);
    const step = form.steps[index];
    if (!step) {
      return null;
    }

    return {
      id: `step-${index}`,
      name: String(step.name || `Step ${index + 1}`),
      step_type: (step.step_type as WorkflowStepValue["step_type"]) || "approval",
      field: typeof step.field === "string" ? step.field : undefined,
      operator: (step.operator as WorkflowStepValue["operator"]) || "eq",
      value: step.value,
      on_true_next_step: typeof step.on_true_next_step === "number" ? step.on_true_next_step : null,
      on_false_next_step: typeof step.on_false_next_step === "number" ? step.on_false_next_step : null,
      approvers: Array.isArray(step.approvers) ? step.approvers.map((item) => String(item)) : [],
      required_approvals: typeof step.required_approvals === "number" ? step.required_approvals : 1,
      escalate_after_hours: typeof step.escalate_after_hours === "number" ? step.escalate_after_hours : undefined,
      escalate_to: typeof step.escalate_to === "string" ? step.escalate_to : undefined,
      recipients: Array.isArray(step.recipients) ? step.recipients.map((item) => String(item)) : [],
      message_template: typeof step.message_template === "string" ? step.message_template : undefined,
    } as WorkflowStepValue;
  }, [form.steps, selectedNodeId]);

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

  function validateSteps(steps: Array<Record<string, unknown>>) {
    const errors: string[] = [];
    if (steps.length === 0) {
      errors.push("Add at least one step.");
    }
    const hasEnd = steps.some((step) => step.step_type === "end");
    if (!hasEnd) {
      errors.push("Add an End step to complete the workflow.");
    }
    const hasApproval = steps.some((step) => step.step_type === "approval");
    if (hasApproval && steps.some((step) => step.step_type === "approval" && Array.isArray(step.approvers) && step.approvers.length === 0)) {
      errors.push("Approval steps need at least one approver.");
    }
    const hasCondition = steps.some((step) => step.step_type === "condition");
    if (hasCondition && steps.some((step) => step.step_type === "condition" && (step.on_true_next_step == null || step.on_false_next_step == null))) {
      errors.push("Condition steps need both true and false branches configured.");
    }
    return errors;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const validationErrors = validateSteps(form.steps);
    if (validationErrors.length > 0) {
      setError(validationErrors.join(" \n"));
      return;
    }
    setSaving(true);
    try {
      await createWorkflowDefinition({
        name: form.name,
        entity_type: form.entity_type,
        description: form.description || undefined,
        steps: form.steps,
        is_active: form.is_active,
      });
      setForm({ name: "", entity_type: "requisition", description: "", steps: [], is_active: true });
      setSelectedNodeId(null);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function updateSelectedNode(changes: Partial<WorkflowStepValue>) {
    if (!selectedNodeId) {
      return;
    }
    const index = form.steps.findIndex((step, stepIndex) => `step-${stepIndex}` === selectedNodeId);
    if (index < 0) {
      return;
    }
    const nextSteps = [...form.steps];
    nextSteps[index] = { ...nextSteps[index], ...changes } as Record<string, unknown>;
    setForm((current) => ({ ...current, steps: nextSteps }));
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
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            Active
          </label>
          <div className="flex items-center gap-2 text-sm">
            <button type="button" className="btn-secondary" onClick={() => setShowJson((value) => !value)}>
              {showJson ? "Hide raw JSON" : "Show raw JSON"}
            </button>
          </div>
          {showJson && (
            <textarea
              className="input-field font-mono text-sm"
              rows={8}
              value={JSON.stringify(form.steps, null, 2)}
              onChange={(e) => setForm({ ...form, steps: JSON.parse(e.target.value || "[]") })}
            />
          )}
          <WorkflowCanvas
            value={form.steps}
            onChange={(steps) => setForm((current) => ({ ...current, steps }))}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
          <div className="rounded-lg border border-slate-200 p-4">
            <h3 className="text-sm font-semibold">Node inspector</h3>
            <div className="mt-3">
              <WorkflowNodeInspector
                selectedNode={selectedNode as WorkflowStepValue | null}
                onUpdate={updateSelectedNode}
              />
            </div>
          </div>
          {error && <p className="whitespace-pre-line text-sm text-red-600">{error}</p>}
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "Creating..." : "Create definition"}
          </button>
        </form>
      </div>
    </div>
  );
}
