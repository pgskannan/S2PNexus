"use client";

import { useCallback, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
  useEdgesState,
  type OnConnect,
  type Connection,
} from "reactflow";
import "reactflow/dist/style.css";

export interface WorkflowStepValue {
  id: string;
  name: string;
  step_type: "condition" | "approval" | "notification" | "auto" | "ai" | "end";
  field?: string;
  operator?: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "in";
  value?: unknown;
  on_true_next_step?: number | null;
  on_false_next_step?: number | null;
  /** Continue target after this step (approval/notification/auto/ai).
   * `allSteps.length` means End. When unset, the engine skips falling into
   * a condition's sibling Yes/No arm. */
  next_step?: number | null;
  approvers?: string[];
  role_code?: string;
  required_approvals?: number;
  escalate_after_hours?: number;
  escalate_to?: string;
  rules?: Record<string, unknown>;
  // Free-text "why this approval" -- shown as a hover tooltip on the canvas
  // node and editable / AI-drafted in the node inspector.
  reason?: string;
  recipients?: string[];
  message_template?: string;
  // True parallel branches: two or more approval/notification/auto steps
  // sharing the same parallel_group run concurrently; the workflow only
  // advances once every approval-type member is satisfied (or rejects
  // immediately if any is rejected). See backend/app/schemas/workflow.py's
  // WorkflowStep docstring for the full semantics.
  parallel_group?: string;
  parallel_next_step?: number | null;
}

interface WorkflowCanvasProps {
  value: Array<Record<string, unknown>>;
  onChange: (value: Array<Record<string, unknown>>) => void;
  selectedNodeId?: string | null;
  onSelectNode?: (id: string | null) => void;
  highlightedNodeId?: string | null;
}

const nodeColors: Record<string, string> = {
  start: "#2563eb",
  condition: "#7c3aed",
  approval: "#d97706",
  notification: "#0f766e",
  auto: "#16a34a",
  ai: "#0891b2",
  end: "#dc2626",
};

const STEP_HINTS: Record<string, string> = {
  start: "Start of the workflow",
  condition: "Routes the flow based on a rule",
  approval: "Requires an approver to sign off",
  notification: "Sends a notification",
  auto: "Approves automatically",
  ai: "AI-assisted decision",
  end: "End of the workflow",
};

/** Custom canvas node: shows the step label plus a hover tooltip explaining
 * why the step exists. The tooltip surfaces the step's `reason` (the editable
 * / AI-drafted "why this approval" text) or, for approval steps with no
 * reason set yet, a gentle nudge to add one in the inspector. */
function WorkflowNode({ data, selected }: NodeProps) {
  const [showTip, setShowTip] = useState(false);
  const label = String(data.label ?? "");
  const color = String(data.color ?? "#64748b");
  const stepType = String(data.step_type ?? "");
  const reason = typeof data.reason === "string" ? data.reason.trim() : "";

  const tipTitle = reason ? "Why this step" : stepType === "approval" ? "Why this approval" : STEP_HINTS[stepType] ?? "Workflow step";

  return (
    <div className="relative" onMouseEnter={() => setShowTip(true)} onMouseLeave={() => setShowTip(false)}>
      <div
        className="rounded-md border bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm transition-shadow hover:shadow-md"
        style={{ borderColor: selected ? "#2563eb" : color, borderLeftWidth: 4 }}
      >
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
          <span className="whitespace-nowrap">{label}</span>
        </span>
      </div>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
      {showTip && (
        <div className="absolute left-1/2 top-full z-50 mt-1.5 w-64 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-2.5 text-left text-xs shadow-xl">
          <p className="font-semibold text-slate-700">{tipTitle}</p>
          {reason ? (
            <p className="mt-0.5 text-slate-600">{reason}</p>
          ) : stepType === "approval" ? (
            <p className="mt-0.5 text-slate-400">
              No reason set — select this step and add one (or use ✨ AI) in the inspector below.
            </p>
          ) : (
            <p className="mt-0.5 text-slate-400">{STEP_HINTS[stepType] ?? "Workflow step"}</p>
          )}
        </div>
      )}
    </div>
  );
}

const nodeTypes = { workflow: WorkflowNode };

/**
 * Turn the step array into a faithful ReactFlow graph.
 *
 * The edges mirror the runtime engine (backend/app/crud/workflow.py
 * `_run_from_step` / `_continue_after_step`):
 *  - a `condition` step routes via its on_true/on_false targets (green "Yes"
 *    / red "No" edges), falling through to the next index when unset;
 *  - steps sharing a `parallel_group` fan out from the group entry to every
 *    member and converge on the group's `parallel_next_step` (or the index
 *    after the last member when unset) -- drawn as purple "‖" edges;
 *  - everything else follows `next_step` when set, otherwise +1 -- but never
 *    draws a linear edge from one Yes/No condition arm into its sibling
 *    (that would imply Yes Approval → No Approval).
 */
function conditionSiblingArm(
  steps: Array<Record<string, unknown>>,
  stepIndex: number
): { sibling: number; merge: number } | null {
  for (const step of steps) {
    if (String(step.step_type) !== "condition") continue;
    const trueT = typeof step.on_true_next_step === "number" ? step.on_true_next_step : null;
    const falseT = typeof step.on_false_next_step === "number" ? step.on_false_next_step : null;
    if (trueT == null || falseT == null || trueT === falseT) continue;
    if (stepIndex === trueT) return { sibling: falseT, merge: Math.max(trueT, falseT) + 1 };
    if (stepIndex === falseT) return { sibling: trueT, merge: Math.max(trueT, falseT) + 1 };
  }
  return null;
}

function continueAfterStep(steps: Array<Record<string, unknown>>, stepIndex: number): number {
  const n = steps.length;
  if (stepIndex < 0 || stepIndex >= n) return n;
  const step = steps[stepIndex];
  if (typeof step.next_step === "number") return step.next_step as number;
  const candidate = stepIndex + 1;
  const siblingInfo = conditionSiblingArm(steps, stepIndex);
  if (siblingInfo && candidate === siblingInfo.sibling) return siblingInfo.merge;
  return candidate;
}

function buildInitialFlow(steps: Array<Record<string, unknown>>) {
  const n = steps.length;
  const COL = 220;
  const ROW = 110;
  const START_X = 24;
  const BASE_Y = 100;

  const groups = new Map<string, number[]>();
  steps.forEach((step, index) => {
    const group = typeof step.parallel_group === "string" ? step.parallel_group.trim() : "";
    if (!group) return;
    const bucket = groups.get(group) ?? [];
    bucket.push(index);
    groups.set(group, bucket);
  });
  const memberSet = new Set<number>();
  groups.forEach((members) => members.forEach((m) => memberSet.add(m)));

  // Simple left-to-right columns. Never stack Start on top of step 0 (that
  // made the canvas look like "one box" after fitView). Condition Yes/No arms
  // share the next column, stacked.
  const positions: Record<number, { x: number; y: number }> = {};
  let col = 1; // column 0 is Start
  let i = 0;
  while (i < n) {
    if (memberSet.has(i)) {
      const members = groups.get(String(steps[i].parallel_group))!;
      members.forEach((memberIndex, offset) => {
        positions[memberIndex] = {
          x: START_X + col * COL,
          y: BASE_Y + (offset - (members.length - 1) / 2) * ROW,
        };
      });
      col += 1;
      i += members.length;
      continue;
    }

    if (positions[i] == null) {
      positions[i] = { x: START_X + col * COL, y: BASE_Y };
      col += 1;
    }

    const step = steps[i];
    if (
      String(step.step_type) === "condition" &&
      typeof step.on_true_next_step === "number" &&
      typeof step.on_false_next_step === "number" &&
      step.on_true_next_step !== step.on_false_next_step
    ) {
      const trueT = step.on_true_next_step as number;
      const falseT = step.on_false_next_step as number;
      const arms = [trueT, falseT].filter((idx) => idx >= 0 && idx < n && positions[idx] == null && !memberSet.has(idx));
      if (arms.length > 0) {
        arms.forEach((armIndex, offset) => {
          positions[armIndex] = {
            x: START_X + col * COL,
            y: BASE_Y + (offset - (arms.length - 1) / 2) * ROW,
          };
        });
        col += 1;
      }
    }

    i += 1;
    while (i < n && positions[i] != null) i += 1;
  }

  for (let idx = 0; idx < n; idx++) {
    if (positions[idx] == null) {
      positions[idx] = { x: START_X + col * COL, y: BASE_Y };
      col += 1;
    }
  }

  const endX = START_X + col * COL;

  const nodes: Node[] = [
    {
      id: "start",
      type: "workflow",
      position: { x: START_X, y: BASE_Y },
      data: { label: "Start", step_type: "start", color: nodeColors.start },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    },
  ];
  steps.forEach((step, index) => {
    const stepType = String(step.step_type || "approval");
    const parallelGroup = typeof step.parallel_group === "string" ? step.parallel_group.trim() : "";
    const label = parallelGroup
      ? `‖ ${String(step.name || `Step ${index + 1}`)} (${parallelGroup})`
      : String(step.name || `Step ${index + 1}`);
    nodes.push({
      id: `step-${index}`,
      type: "workflow",
      position: positions[index],
      data: {
        label,
        step_type: stepType,
        color: nodeColors[stepType] || nodeColors.approval,
        reason: typeof step.reason === "string" && step.reason ? step.reason : undefined,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
  });
  nodes.push({
    id: "end",
    type: "workflow",
    position: { x: endX, y: BASE_Y },
    data: { label: "End", step_type: "end", color: nodeColors.end },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  });

  const edges: Edge[] = [];
  const seen = new Set<string>();
  const addEdge = (source: string, target: string, opts: Partial<Edge> = {}) => {
    if (!source || !target || source === target) return;
    const key = `${source}->${target}`;
    if (seen.has(key)) return;
    seen.add(key);
    edges.push({
      id: `edge-${edges.length}`,
      source,
      target,
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
      style: { strokeWidth: 1.5, stroke: "#94a3b8", ...(opts.style as object) },
      ...opts,
    } as Edge);
  };

  const resolveTarget = (indexOrNull: number | null | undefined, fallbackIndex: number): string => {
    const target = indexOrNull == null ? fallbackIndex : indexOrNull;
    return target >= n ? "end" : `step-${target}`;
  };

  const groupEntry: Record<number, string> = {};
  groups.forEach((members) => {
    const first = members[0];
    groupEntry[first] = first === 0 ? "start" : `step-${first - 1}`;
  });

  const conditionTargets = new Set<number>();
  steps.forEach((step) => {
    if (String(step.step_type) !== "condition") return;
    if (typeof step.on_true_next_step === "number" && step.on_true_next_step < n) {
      conditionTargets.add(step.on_true_next_step);
    }
    if (typeof step.on_false_next_step === "number" && step.on_false_next_step < n) {
      conditionTargets.add(step.on_false_next_step);
    }
  });

  for (let index = 0; index < n; index++) {
    const step = steps[index];
    const stepType = String(step.step_type || "approval");
    const id = `step-${index}`;

    if (memberSet.has(index)) {
      const members = groups.get(String(step.parallel_group))!;
      const entry = groupEntry[index];
      if (entry) {
        members.forEach((memberIndex) =>
          addEdge(entry, `step-${memberIndex}`, {
            label: "‖",
            style: { stroke: nodeColors.condition, strokeWidth: 1.5 },
            labelStyle: { fill: nodeColors.condition, fontWeight: 700, fontSize: 11 },
          })
        );
      }
      const parallelNext = typeof step.parallel_next_step === "number" ? (step.parallel_next_step as number) : null;
      const fallback = Math.max(...members) + 1;
      addEdge(id, resolveTarget(parallelNext, fallback), {
        label: "‖",
        style: { stroke: nodeColors.condition, strokeWidth: 1.5 },
        labelStyle: { fill: nodeColors.condition, fontWeight: 700, fontSize: 11 },
      });
    } else if (stepType === "condition") {
      if (index === 0 || !conditionTargets.has(index)) {
        addEdge(index === 0 ? "start" : `step-${index - 1}`, id);
      }
      addEdge(id, resolveTarget(typeof step.on_true_next_step === "number" ? step.on_true_next_step : null, index + 1), {
        label: "Yes",
        style: { stroke: "#16a34a", strokeWidth: 1.75 },
        labelStyle: { fill: "#16a34a", fontWeight: 700, fontSize: 11 },
      });
      addEdge(id, resolveTarget(typeof step.on_false_next_step === "number" ? step.on_false_next_step : null, index + 1), {
        label: "No",
        style: { stroke: "#dc2626", strokeWidth: 1.75 },
        labelStyle: { fill: "#dc2626", fontWeight: 700, fontSize: 11 },
      });
    } else {
      const prevIsCondition = index > 0 && String(steps[index - 1].step_type) === "condition";
      const prevIsGroupMember = memberSet.has(index - 1);
      if (!prevIsCondition && !prevIsGroupMember && !conditionTargets.has(index)) {
        addEdge(index === 0 ? "start" : `step-${index - 1}`, id);
      }
      const continueTo = continueAfterStep(steps, index);
      addEdge(id, resolveTarget(continueTo, continueTo));
    }
  }

  if (n === 0) {
    addEdge("start", "end");
  }

  return { nodes, edges };
}

function mapStepsToValue(steps: Array<Record<string, unknown>>): WorkflowStepValue[] {
  return steps.map((step, index) => ({
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
  }));
}

function mapValueToSteps(values: WorkflowStepValue[]): Array<Record<string, unknown>> {
  return values.map((step) => ({
    name: step.name,
    step_type: step.step_type,
    field: step.field,
    operator: step.operator,
    value: step.value,
    on_true_next_step: step.on_true_next_step,
    on_false_next_step: step.on_false_next_step,
    next_step: step.next_step,
    approvers: step.approvers || [],
    role_code: step.role_code,
    required_approvals: step.required_approvals || 1,
    escalate_after_hours: step.escalate_after_hours,
    escalate_to: step.escalate_to,
    rules: step.rules,
    reason: step.reason || undefined,
    recipients: step.recipients || [],
    message_template: step.message_template,
    parallel_group: step.parallel_group || undefined,
    parallel_next_step: step.parallel_next_step ?? undefined,
  }));
}

export function WorkflowCanvas({ value, onChange, selectedNodeId, onSelectNode, highlightedNodeId }: WorkflowCanvasProps) {
  // Derived directly from the `value` prop on every render rather than mirrored
  // into local state -- steps can change from three different places (this
  // component's own "Add X" buttons, the Node inspector editing a field, or
  // switching which definition is being edited), and a local copy that only
  // seeds from props once on mount would go stale for the other two.
  const steps = useMemo(() => mapStepsToValue(value as Array<Record<string, unknown>>), [value]);
  const [edges, setEdges] = useEdgesState([]);

  const addStep = useCallback((stepType: WorkflowStepValue["step_type"]) => {
    const nextSteps = [...steps, {
      id: `step-${steps.length}`,
      name: `${stepType[0].toUpperCase()}${stepType.slice(1)} ${steps.length + 1}`,
      step_type: stepType === "end" ? "approval" : stepType,
    }];
    onChange(mapValueToSteps(nextSteps));
  }, [onChange, steps]);

  // One-click starting point for "run these at the same time" -- adds two
  // linked approval steps sharing a fresh parallel_group instead of making
  // the admin add two separate steps and hand-type a matching group name
  // into each one's inspector (the entry point that was hard to find,
  // 2026-08-02 feedback). Select each new node afterward to name it, assign
  // approvers, and add a third+ branch the same way (Add approval, then set
  // the same group name in its inspector).
  const addParallelBranches = useCallback(() => {
    const groupKey = `parallel_${Date.now().toString(36)}`;
    const base = steps.length;
    const nextSteps = [
      ...steps,
      {
        id: `step-${base}`,
        name: "Branch A",
        step_type: "approval" as const,
        parallel_group: groupKey,
        parallel_next_step: null,
      },
      {
        id: `step-${base + 1}`,
        name: "Branch B",
        step_type: "approval" as const,
        parallel_group: groupKey,
        parallel_next_step: null,
      },
    ];
    onChange(mapValueToSteps(nextSteps));
    onSelectNode?.(`step-${base}`);
  }, [onChange, onSelectNode, steps]);

  const removeStep = useCallback((index: number) => {
    if (index < 0 || index >= steps.length) return;
    // Condition steps reference other steps by array index
    // (on_true_next_step / on_false_next_step -- see crud/workflow.py's
    // _run_from_step), so removing a step must shift every reference above
    // it down by one, and null out any reference that pointed at the step
    // being removed (the branch is now undefined; the engine falls through
    // to step_index + 1 by default, and the designer flags it via
    // validateSteps' "need both true and false branches" check so it's not
    // silently wrong -- it's visibly incomplete).
    const adjust = (v?: number | null) => {
      if (v == null) return v ?? null;
      if (v === index) return null;
      if (v > index) return v - 1;
      return v;
    };
    const nextSteps = steps
      .filter((_, i) => i !== index)
      .map((step) => ({
        ...step,
        on_true_next_step: adjust(step.on_true_next_step),
        on_false_next_step: adjust(step.on_false_next_step),
        next_step: adjust(step.next_step),
        // parallel_next_step is an index reference too (see
        // ParallelGroupFields in WorkflowNodeInspector.tsx) -- same
        // shift-down / null-out-if-removed treatment applies.
        parallel_next_step: adjust(step.parallel_next_step),
      }));
    onChange(mapValueToSteps(nextSteps));
    onSelectNode?.(null);
  }, [onChange, onSelectNode, steps]);

  const handleConnect: OnConnect = useCallback((params: Connection) => {
    const edge: Edge = {
      id: `edge-${params.source}-${params.target}`,
      source: params.source || "",
      target: params.target || "",
      markerEnd: { type: MarkerType.ArrowClosed },
      label: params.source === "start" ? "start" : undefined,
    };
    setEdges((eds) => [...eds, edge]);
  }, [setEdges]);

  const flowNodes = useMemo(() => {
    const baseNodes = buildInitialFlow(mapValueToSteps(steps) as Array<Record<string, unknown>>).nodes;
    return baseNodes.map((node) => {
      if (node.id === highlightedNodeId) {
        return { ...node, className: "ring-2 ring-yellow-400" };
      }
      if (selectedNodeId && node.id === selectedNodeId) {
        return { ...node, className: "ring-2 ring-blue-400" };
      }
      return node;
    });
  }, [highlightedNodeId, selectedNodeId, steps]);

  const flowEdges = useMemo(() => {
    const baseEdges = buildInitialFlow(mapValueToSteps(steps) as Array<Record<string, unknown>>).edges;
    return baseEdges;
  }, [steps]);

  const selectedStepIndex = selectedNodeId?.startsWith("step-") ? Number(selectedNodeId.slice("step-".length)) : null;
  const canDeleteSelected = selectedStepIndex !== null && !Number.isNaN(selectedStepIndex) && selectedStepIndex < steps.length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {(["condition", "approval", "notification", "auto", "ai"] as const).map((type) => (
          <button key={type} type="button" onClick={() => addStep(type)} className="btn-secondary">
            Add {type === "ai" ? "AI rule" : type}
          </button>
        ))}
        <button
          type="button"
          onClick={addParallelBranches}
          className="btn-secondary border-purple-200 text-purple-700 hover:bg-purple-50"
          title="Add two approval steps that run at the same time"
        >
          ‖ Add parallel branches
        </button>
        <button
          type="button"
          className="btn-secondary ml-auto border-red-200 text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!canDeleteSelected}
          onClick={() => {
            if (selectedStepIndex === null) return;
            if (!confirm("Remove this step? Any condition branches pointing at it will need to be reconnected.")) return;
            removeStep(selectedStepIndex);
          }}
        >
          Delete selected step
        </button>
      </div>
      <div className="h-[420px] rounded-lg border border-slate-200 bg-white">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onConnect={handleConnect}
          onNodeClick={(event, node) => onSelectNode?.(node.id)}
          fitView
          fitViewOptions={{ padding: 0.2, minZoom: 0.45, maxZoom: 1.25 }}
          minZoom={0.35}
          maxZoom={1.5}
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{ type: "smoothstep" }}
        >
          <Background gap={18} size={1} color="#e2e8f0" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}
