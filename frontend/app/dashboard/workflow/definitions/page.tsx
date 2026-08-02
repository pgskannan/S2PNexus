"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { MousePointerClick, X } from "lucide-react";
import { createWorkflowDefinition, deleteWorkflowDefinition, extractErrorMessage, listWorkflowDefinitions, updateWorkflowDefinition } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
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
  const [editingId, setEditingId] = useState<string | null>(null);
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator" || user?.is_superuser === true;

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
      next_step: typeof step.next_step === "number" ? step.next_step : null,
      approvers: Array.isArray(step.approvers) ? step.approvers.map((item) => String(item)) : [],
      role_code: typeof step.role_code === "string" && step.role_code ? step.role_code : undefined,
      required_approvals: typeof step.required_approvals === "number" ? step.required_approvals : 1,
      escalate_after_hours: typeof step.escalate_after_hours === "number" ? step.escalate_after_hours : undefined,
      escalate_to: typeof step.escalate_to === "string" ? step.escalate_to : undefined,
      rules: step.rules && typeof step.rules === "object" && !Array.isArray(step.rules) ? (step.rules as Record<string, unknown>) : undefined,
      reason: typeof step.reason === "string" ? step.reason : undefined,
      recipients: Array.isArray(step.recipients) ? step.recipients.map((item) => String(item)) : [],
      message_template: typeof step.message_template === "string" ? step.message_template : undefined,
      parallel_group: typeof step.parallel_group === "string" && step.parallel_group ? step.parallel_group : undefined,
      parallel_next_step: typeof step.parallel_next_step === "number" ? step.parallel_next_step : null,
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

  const groupedDefinitions = useMemo(() => {
    const groups = new Map<string, WorkflowDefinition[]>();
    for (const definition of definitions) {
      const key = `${definition.entity_type}::${definition.name}`;
      const bucket = groups.get(key) ?? [];
      bucket.push(definition);
      groups.set(key, bucket);
    }
    return Array.from(groups.entries())
      .map(([key, items]) => ({
        key,
        items: [...items].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
      }))
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [definitions]);

  useEffect(() => {
    load();
  }, []);

  function validateSteps(steps: Array<Record<string, unknown>>) {
    const errors: string[] = [];
    if (steps.length === 0) {
      errors.push("Add at least one step.");
    }
    // NOTE: there used to be a check here requiring a step with
    // step_type === "end", but "end" was never a real step type -- the
    // backend schema (schemas/workflow.py STEP_TYPES) and the step-type
    // picker in WorkflowNodeInspector.tsx only support
    // condition/approval/notification. That meant this validation could
    // never pass, so no workflow definition could ever be saved through this
    // page. A workflow instance simply completes when it runs out of steps,
    // so no explicit "end" marker is needed.
    const hasApproval = steps.some((step) => step.step_type === "approval");
    if (
      hasApproval &&
      steps.some(
        (step) =>
          step.step_type === "approval" &&
          Array.isArray(step.approvers) &&
          step.approvers.length === 0 &&
          !(typeof step.role_code === "string" && step.role_code)
      )
    ) {
      errors.push("Approval steps need at least one approver, or a role to resolve approvers from.");
    }
    const hasCondition = steps.some((step) => step.step_type === "condition");
    if (hasCondition && steps.some((step) => step.step_type === "condition" && (step.on_true_next_step == null || step.on_false_next_step == null))) {
      errors.push("Condition steps need both true and false branches configured.");
    }

    // Mirror the backend's WorkflowDefinitionCreate._validate_parallel_groups
    // checks client-side so mistakes surface here instead of as a 422 after
    // "Save as new version".
    const groups = new Map<string, number[]>();
    steps.forEach((step, index) => {
      if (typeof step.parallel_group !== "string" || !step.parallel_group) return;
      if (!["approval", "notification", "auto"].includes(String(step.step_type))) {
        errors.push(`Step ${index + 1} ("${step.name}"): parallel group only works on approval, notification, or auto steps.`);
        return;
      }
      const bucket = groups.get(step.parallel_group) ?? [];
      bucket.push(index);
      groups.set(step.parallel_group, bucket);
    });
    groups.forEach((memberIndices, groupKey) => {
      if (memberIndices.length < 2) {
        errors.push(`Parallel group "${groupKey}" only has one step -- add it to at least one more step, or clear it.`);
        return;
      }
      const nextSteps = new Set(memberIndices.map((i) => steps[i].parallel_next_step ?? null));
      if (nextSteps.size > 1) {
        errors.push(`Every step in parallel group "${groupKey}" must have the same "Continue to" target.`);
      }
    });

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
      const payload = {
        name: form.name,
        entity_type: form.entity_type,
        description: form.description || undefined,
        steps: form.steps,
        is_active: form.is_active,
      };
      if (editingId) {
        await updateWorkflowDefinition(editingId, payload);
      } else {
        await createWorkflowDefinition(payload);
      }
      setForm({ name: "", entity_type: "requisition", description: "", steps: [], is_active: true });
      setSelectedNodeId(null);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function startEditing(definition: WorkflowDefinition) {
    setEditingId(definition.id);
    setForm({
      name: definition.name,
      entity_type: definition.entity_type,
      description: definition.description ?? "",
      steps: definition.steps,
      is_active: definition.is_active,
    });
    setSelectedNodeId(null);
  }

  function cancelEditing() {
    setEditingId(null);
    setForm({ name: "", entity_type: "requisition", description: "", steps: [], is_active: true });
    setSelectedNodeId(null);
  }

  async function handleDelete(definition: WorkflowDefinition) {
    if (!confirm(`Delete workflow definition "${definition.name}"?`)) return;
    try {
      await deleteWorkflowDefinition(definition.id);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
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

      <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="card overflow-x-auto p-0">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Entity type</th>
                <th className="px-4 py-3">Status</th>
                {isAdmin && <th className="px-4 py-3">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td className="px-4 py-4 text-slate-400" colSpan={isAdmin ? 4 : 3}>
                    Loading...
                  </td>
                </tr>
              )}
              {!loading && definitions.length === 0 && (
                <tr>
                  <td className="px-4 py-4 text-slate-400" colSpan={isAdmin ? 4 : 3}>
                    No workflow definitions yet.
                  </td>
                </tr>
              )}
              {groupedDefinitions.map((group) => (
                <GroupRows
                  key={group.key}
                  group={group}
                  isAdmin={isAdmin}
                  editingId={editingId}
                  onEdit={startEditing}
                  onDelete={handleDelete}
                />
              ))}
            </tbody>
          </table>
        </div>

        <div className="card space-y-4">
          <h2 className="text-lg font-semibold">{editingId ? "Edit definition (publishes a new version)" : "Create definition"}</h2>
          {editingId && (
            <p className="text-sm text-slate-500">
              Saving publishes a new version and archives the current one. Workflows already in flight keep running the
              version they started on.
            </p>
          )}
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
        </div>
      </div>

      {/* Designer: canvas on top, node inspector docked as a bottom panel.
          The inspector is the one place a condition's Yes/No branch targets and
          a step's parallel group are set, so it gets a dedicated full-width
          panel instead of being buried in the form column (2026-08-02). */}
      <div className="card overflow-hidden">
        <div className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-slate-900">Workflow canvas</h3>
              <p className="text-sm text-slate-500">
                Build the flow left to right. Conditions route via green Yes / red No branches; steps sharing a purple
                “‖” group run in parallel. Click a step to edit it in the inspector panel below.
              </p>
            </div>
          </div>
          <div className="mt-3">
            <WorkflowCanvas
              value={form.steps}
              onChange={(steps) => setForm((current) => ({ ...current, steps }))}
              selectedNodeId={selectedNodeId}
              onSelectNode={setSelectedNodeId}
            />
          </div>
        </div>

        {/* Bottom-docked node inspector panel */}
        <div className="border-t border-slate-200 bg-slate-50">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2.5">
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <span className="shrink-0 font-semibold text-slate-700">Node inspector</span>
              {selectedNode && (
                <>
                  <span className="text-slate-300">·</span>
                  <span className="truncate text-slate-500">
                    Editing <span className="font-medium text-slate-700">{selectedNode.name}</span>
                  </span>
                </>
              )}
            </div>
            {selectedNode && (
              <button
                type="button"
                className="flex shrink-0 items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
                onClick={() => setSelectedNodeId(null)}
              >
                <X className="h-3.5 w-3.5" />
                Close
              </button>
            )}
          </div>
          {selectedNode ? (
            <div className="max-h-[520px] overflow-y-auto p-4">
              <WorkflowNodeInspector
                selectedNode={selectedNode as WorkflowStepValue | null}
                onUpdate={updateSelectedNode}
                entityType={form.entity_type}
                allSteps={form.steps}
              />
            </div>
          ) : (
            <div className="flex items-center gap-2 p-4 text-sm text-slate-500">
              <MousePointerClick className="h-4 w-4 text-slate-400" />
              Select a step on the canvas to edit its properties in this panel.
            </div>
          )}
        </div>
      </div>

          {error && <p className="whitespace-pre-line text-sm text-red-600">{error}</p>}
          <div className="flex gap-3">
            <button type="submit" disabled={saving} className="btn-primary">
              {saving ? "Saving..." : editingId ? "Save as new version" : "Create definition"}
            </button>
            {editingId && (
              <button type="button" className="btn-secondary" onClick={cancelEditing}>
                Cancel
              </button>
            )}
          </div>
      </form>
    </div>
  );
}

function GroupRows({
  group,
  isAdmin,
  editingId,
  onEdit,
  onDelete,
}: {
  group: { key: string; items: WorkflowDefinition[] };
  isAdmin: boolean;
  editingId: string | null;
  onEdit: (definition: WorkflowDefinition) => void;
  onDelete: (definition: WorkflowDefinition) => void;
}) {
  const [entityType, name] = group.key.split("::");
  return (
    <>
      <tr className="bg-slate-50">
        <td className="px-4 py-2 text-xs font-semibold uppercase text-slate-500" colSpan={isAdmin ? 4 : 3}>
          {name} <span className="font-normal normal-case">({entityType})</span>
          {group.items.length > 1 && (
            <span className="ml-2 font-normal normal-case text-slate-400">{group.items.length} versions</span>
          )}
        </td>
      </tr>
      {group.items.map((definition, index) => {
        const isArchived = definition.status === "archived" || !definition.is_active;
        return (
          <tr key={definition.id} className={`hover:bg-slate-50 ${editingId === definition.id ? "bg-blue-50" : ""}`}>
            <td className="px-4 py-3">
              <span className="font-medium">{index === 0 ? "Current" : `Version ${group.items.length - index}`}</span>
              <span className="ml-2 text-xs text-slate-400">
                {new Date(definition.created_at).toLocaleDateString()}
              </span>
            </td>
            <td className="px-4 py-3">{definition.entity_type}</td>
            <td className="px-4 py-3">
              <span
                className={`badge ${
                  isArchived ? "bg-slate-100 text-slate-600" : "bg-green-100 text-green-700"
                }`}
              >
                {isArchived ? "Archived" : "Active"}
              </span>
            </td>
            {isAdmin && (
              <td className="px-4 py-3">
                <div className="flex gap-3">
                  {!isArchived && (
                    <button type="button" className="text-xs text-blue-600 hover:underline" onClick={() => onEdit(definition)}>
                      Edit
                    </button>
                  )}
                  <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => onDelete(definition)}>
                    Delete
                  </button>
                </div>
              </td>
            )}
          </tr>
        );
      })}
    </>
  );
}
