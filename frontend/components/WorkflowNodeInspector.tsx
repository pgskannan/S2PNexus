import type { WorkflowStepValue } from "./WorkflowCanvas";

interface WorkflowNodeInspectorProps {
  selectedNode: WorkflowStepValue | null;
  onUpdate: (changes: Partial<WorkflowStepValue>) => void;
}

export function WorkflowNodeInspector({ selectedNode, onUpdate }: WorkflowNodeInspectorProps) {
  if (!selectedNode) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        Select a step to edit its properties.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="label">Step name</label>
        <input
          className="input-field"
          value={selectedNode.name}
          onChange={(event) => onUpdate({ name: event.target.value })}
        />
      </div>

      {selectedNode.step_type === "condition" && (
        <>
          <div>
            <label className="label">Field</label>
            <input
              className="input-field"
              value={selectedNode.field || ""}
              onChange={(event) => onUpdate({ field: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Operator</label>
            <select
              className="input-field"
              value={selectedNode.operator || "eq"}
              onChange={(event) => onUpdate({ operator: event.target.value as WorkflowStepValue["operator"] })}
            >
              <option value="eq">eq</option>
              <option value="neq">neq</option>
              <option value="gt">gt</option>
              <option value="gte">gte</option>
              <option value="lt">lt</option>
              <option value="lte">lte</option>
              <option value="in">in</option>
            </select>
          </div>
          <div>
            <label className="label">Value</label>
            <input
              className="input-field"
              value={typeof selectedNode.value === "string" ? selectedNode.value : ""}
              onChange={(event) => onUpdate({ value: event.target.value })}
            />
          </div>
        </>
      )}

      {selectedNode.step_type === "approval" && (
        <>
          <div>
            <label className="label">Approvers (comma separated UUIDs)</label>
            <input
              className="input-field"
              value={(selectedNode.approvers || []).join(",")}
              onChange={(event) =>
                onUpdate({
                  approvers: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div>
            <label className="label">Required approvals</label>
            <input
              className="input-field"
              type="number"
              min={1}
              value={selectedNode.required_approvals || 1}
              onChange={(event) => onUpdate({ required_approvals: Number(event.target.value) })}
            />
          </div>
          <div>
            <label className="label">Escalate after hours</label>
            <input
              className="input-field"
              type="number"
              min={1}
              value={selectedNode.escalate_after_hours ?? ""}
              onChange={(event) => onUpdate({ escalate_after_hours: event.target.value ? Number(event.target.value) : undefined })}
            />
          </div>
          <div>
            <label className="label">Escalate to (UUID)</label>
            <input
              className="input-field"
              value={selectedNode.escalate_to || ""}
              onChange={(event) => onUpdate({ escalate_to: event.target.value || undefined })}
            />
          </div>
        </>
      )}

      {selectedNode.step_type === "notification" && (
        <>
          <div>
            <label className="label">Recipients (comma separated UUIDs)</label>
            <input
              className="input-field"
              value={(selectedNode.recipients || []).join(",")}
              onChange={(event) =>
                onUpdate({
                  recipients: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div>
            <label className="label">Message template</label>
            <textarea
              className="input-field"
              rows={4}
              value={selectedNode.message_template || ""}
              onChange={(event) => onUpdate({ message_template: event.target.value })}
            />
          </div>
        </>
      )}
    </div>
  );
}
