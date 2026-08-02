"use client";

import { useCallback, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  type Edge,
  type Node,
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
  approvers?: string[];
  role_code?: string;
  required_approvals?: number;
  escalate_after_hours?: number;
  escalate_to?: string;
  rules?: Record<string, unknown>;
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

function buildInitialFlow(steps: Array<Record<string, unknown>>) {
  const startNode = {
    id: "start",
    type: "default",
    position: { x: 40, y: 60 },
    data: { label: "Start", step_type: "start", color: nodeColors.start },
  };

  const nodes: Node[] = [startNode];
  const edges: Edge[] = [];

  steps.forEach((step, index) => {
    const id = `step-${index}`;
    const stepType = String(step.step_type || "approval");
    const parallelGroup = typeof step.parallel_group === "string" ? step.parallel_group : "";
    const label = parallelGroup
      ? `‖ ${String(step.name || `Step ${index + 1}`)} (${parallelGroup})`
      : String(step.name || `Step ${index + 1}`);
    const node = {
      id,
      type: "default",
      position: { x: 260 + Math.floor(index / 2) * 220, y: 60 + (index % 2) * 140 },
      data: {
        label,
        step_type: stepType,
        color: nodeColors[stepType] || nodeColors.approval,
      },
    };
    nodes.push(node);
    edges.push({
      id: `edge-${nodes.length - 1}`,
      source: index === 0 ? startNode.id : `step-${index - 1}`,
      target: id,
      markerEnd: { type: MarkerType.ArrowClosed },
      label: stepType === "condition" ? "next" : parallelGroup ? "‖" : undefined,
    });
  });

  const endNode = {
    id: "end",
    type: "default",
    position: { x: 260 + Math.floor((steps.length || 0) / 2) * 220, y: 60 + ((steps.length || 0) % 2) * 140 },
    data: { label: "End", step_type: "end", color: nodeColors.end },
  };
  nodes.push(endNode);
  if (steps.length > 0) {
    edges.push({
      id: `edge-end-${steps.length}`,
      source: `step-${steps.length - 1}`,
      target: endNode.id,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  } else {
    edges.push({
      id: "edge-start-end",
      source: startNode.id,
      target: endNode.id,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
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
    approvers: Array.isArray(step.approvers) ? step.approvers.map((item) => String(item)) : [],
    role_code: typeof step.role_code === "string" && step.role_code ? step.role_code : undefined,
    required_approvals: typeof step.required_approvals === "number" ? step.required_approvals : 1,
    escalate_after_hours: typeof step.escalate_after_hours === "number" ? step.escalate_after_hours : undefined,
    escalate_to: typeof step.escalate_to === "string" ? step.escalate_to : undefined,
    rules: step.rules && typeof step.rules === "object" && !Array.isArray(step.rules) ? (step.rules as Record<string, unknown>) : undefined,
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
    approvers: step.approvers || [],
    role_code: step.role_code,
    required_approvals: step.required_approvals || 1,
    escalate_after_hours: step.escalate_after_hours,
    escalate_to: step.escalate_to,
    rules: step.rules,
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
          onConnect={handleConnect}
          onNodeClick={(event, node) => onSelectNode?.(node.id)}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
