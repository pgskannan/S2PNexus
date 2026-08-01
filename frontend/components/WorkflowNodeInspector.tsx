"use client";

import { useEffect, useState } from "react";
import type { WorkflowStepValue } from "./WorkflowCanvas";
import UserPicker from "@/components/UserPicker";
import { resolveApprovers } from "@/lib/api";
import { APPROVER_ROLE_CODES, type ResolvedApprover } from "@/lib/types";

interface WorkflowNodeInspectorProps {
  selectedNode: WorkflowStepValue | null;
  onUpdate: (changes: Partial<WorkflowStepValue>) => void;
}

function RoleResolutionPreview({ roleCode, amount }: { roleCode: string; amount: string }) {
  const [resolved, setResolved] = useState<ResolvedApprover[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!roleCode) {
      setResolved([]);
      return;
    }
    setLoading(true);
    setError(null);
    resolveApprovers({ role_code: roleCode, amount: amount || undefined })
      .then((res) => {
        if (!cancelled) setResolved(res.approvers);
      })
      .catch(() => {
        if (!cancelled) setError("Could not resolve approvers.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [roleCode, amount]);

  if (!roleCode) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
      {loading && <span className="text-slate-500">Resolving...</span>}
      {error && <span className="text-red-600">{error}</span>}
      {!loading && !error && resolved.length === 0 && (
        <span className="text-amber-700">
          No active approver seed matches this role (and amount) yet. Configure one in the approver matrix, or this step
          will be skipped at runtime.
        </span>
      )}
      {!loading && !error && resolved.length > 0 && (
        <div>
          <span className="text-slate-500">Currently resolves to:</span>
          <ul className="mt-1 space-y-0.5">
            {resolved.map((a) => (
              <li key={a.user_id} className="text-slate-700">
                {a.display_name}
                {a.is_primary_approver ? " (primary)" : ""}
                {a.backup_approver_user_id ? " · has backup" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function WorkflowNodeInspector({ selectedNode, onUpdate }: WorkflowNodeInspectorProps) {
  const [previewAmount, setPreviewAmount] = useState("");
  const [escalateRole, setEscalateRole] = useState("");
  const [escalateResolvedName, setEscalateResolvedName] = useState<string | null>(null);

  const approverMode: "users" | "role" = selectedNode?.role_code ? "role" : "users";

  useEffect(() => {
    // Reset per-node transient UI state when selection changes.
    setPreviewAmount("");
    setEscalateRole("");
    setEscalateResolvedName(null);
  }, [selectedNode?.id]);

  if (!selectedNode) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
        Select a step to edit its properties.
      </div>
    );
  }

  async function pickEscalateByRole(role: string) {
    setEscalateRole(role);
    setEscalateResolvedName(null);
    if (!role) return;
    try {
      const res = await resolveApprovers({ role_code: role });
      const primary = res.approvers[0];
      if (primary) {
        // The backend step schema stores escalate_to as a single user id (there
        // is no escalate_to_role field), so role selection here resolves at
        // design time and stores the resolved user.
        onUpdate({ escalate_to: primary.user_id });
        setEscalateResolvedName(primary.display_name);
      } else {
        setEscalateResolvedName("");
      }
    } catch {
      setEscalateResolvedName("");
    }
  }

  const rules = (selectedNode.rules || {}) as Record<string, unknown>;
  const categoryRouting = (rules.category_routing || {}) as Record<string, string>;

  function updateRules(changes: Record<string, unknown>) {
    const next = { ...rules, ...changes };
    for (const key of Object.keys(next)) {
      if (next[key] === undefined || next[key] === "") delete next[key];
    }
    onUpdate({ rules: next });
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
            <label className="label">Approvers</label>
            <div className="mb-2 flex gap-2">
              <button
                type="button"
                className={approverMode === "users" ? "btn-primary" : "btn-secondary"}
                onClick={() => onUpdate({ role_code: undefined })}
              >
                Named users
              </button>
              <button
                type="button"
                className={approverMode === "role" ? "btn-primary" : "btn-secondary"}
                onClick={() => onUpdate({ role_code: APPROVER_ROLE_CODES[0], approvers: [] })}
              >
                By role
              </button>
            </div>

            {approverMode === "users" && (
              <UserPicker
                value={selectedNode.approvers || []}
                onChange={(ids) => onUpdate({ approvers: ids })}
                multiple
              />
            )}

            {approverMode === "role" && (
              <div className="space-y-2">
                <select
                  className="input-field"
                  value={selectedNode.role_code || ""}
                  onChange={(event) => onUpdate({ role_code: event.target.value, approvers: [] })}
                >
                  {APPROVER_ROLE_CODES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
                <div>
                  <label className="label">Preview with amount (optional)</label>
                  <input
                    className="input-field"
                    type="number"
                    min={0}
                    placeholder="e.g. 1500"
                    value={previewAmount}
                    onChange={(event) => setPreviewAmount(event.target.value)}
                  />
                </div>
                <RoleResolutionPreview roleCode={selectedNode.role_code || ""} amount={previewAmount} />
              </div>
            )}
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
            <p className="mt-1 text-xs text-slate-500">
              If an SLA definition exists for this document type and role, the SLA target takes precedence over this
              value at runtime.
            </p>
          </div>
          <div>
            <label className="label">Escalate to</label>
            <div className="mb-2 flex gap-2">
              <button
                type="button"
                className={!escalateRole ? "btn-primary" : "btn-secondary"}
                onClick={() => {
                  setEscalateRole("");
                  setEscalateResolvedName(null);
                }}
              >
                Named user
              </button>
              <button
                type="button"
                className={escalateRole ? "btn-primary" : "btn-secondary"}
                onClick={() => pickEscalateByRole(APPROVER_ROLE_CODES[0])}
              >
                By role
              </button>
            </div>
            {!escalateRole && (
              <UserPicker
                value={selectedNode.escalate_to ? [selectedNode.escalate_to] : []}
                onChange={(ids) => onUpdate({ escalate_to: ids.length ? ids[0] : undefined })}
                multiple={false}
              />
            )}
            {escalateRole && (
              <div className="space-y-2">
                <select
                  className="input-field"
                  value={escalateRole}
                  onChange={(event) => pickEscalateByRole(event.target.value)}
                >
                  {APPROVER_ROLE_CODES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
                {escalateResolvedName ? (
                  <p className="text-xs text-slate-500">
                    Stored as the resolved user: <span className="text-slate-700">{escalateResolvedName}</span> (the
                    engine escalates to a specific user, so the role is resolved now, not at runtime).
                  </p>
                ) : escalateResolvedName === "" ? (
                  <p className="text-xs text-amber-700">No active approver seed for this role — pick a named user instead.</p>
                ) : null}
              </div>
            )}
          </div>
        </>
      )}

      {selectedNode.step_type === "auto" && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
          Deterministic auto-approval: this step approves automatically and records an AUTO_APPROVED audit event. No
          configuration needed beyond the step name.
        </div>
      )}

      {selectedNode.step_type === "ai" && (
        <>
          <div>
            <label className="label">Auto-approve below amount</label>
            <input
              className="input-field"
              type="number"
              min={0}
              placeholder="500.00 (default)"
              value={typeof rules.auto_approve_below === "string" || typeof rules.auto_approve_below === "number" ? String(rules.auto_approve_below) : ""}
              onChange={(event) => updateRules({ auto_approve_below: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Supplier risk threshold</label>
            <input
              className="input-field"
              type="number"
              min={0}
              max={100}
              placeholder="70 (default)"
              value={typeof rules.supplier_risk_threshold === "string" || typeof rules.supplier_risk_threshold === "number" ? String(rules.supplier_risk_threshold) : ""}
              onChange={(event) => updateRules({ supplier_risk_threshold: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Category routing</label>
            <div className="space-y-2">
              {Object.entries(categoryRouting).map(([category, target]) => (
                <div key={category} className="flex items-center gap-2">
                  <input className="input-field" value={category} readOnly />
                  <input
                    className="input-field"
                    value={target}
                    onChange={(event) =>
                      updateRules({ category_routing: { ...categoryRouting, [category]: event.target.value } })
                    }
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      const next = { ...categoryRouting };
                      delete next[category];
                      updateRules({ category_routing: Object.keys(next).length ? next : undefined });
                    }}
                  >
                    Remove
                  </button>
                </div>
              ))}
              <AddCategoryRoutingRow
                onAdd={(category, target) =>
                  updateRules({ category_routing: { ...categoryRouting, [category]: target } })
                }
              />
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Routes documents in a category to a named node (e.g. IT → risk_review). If not auto-approved, the step
              falls through to an approval for the AI-suggested role.
            </p>
          </div>
        </>
      )}

      {selectedNode.step_type === "notification" && (
        <>
          <div>
            <label className="label">Recipients</label>
            <UserPicker
              value={selectedNode.recipients || []}
              onChange={(ids) => onUpdate({ recipients: ids })}
              multiple
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

function AddCategoryRoutingRow({ onAdd }: { onAdd: (category: string, target: string) => void }) {
  const [category, setCategory] = useState("");
  const [target, setTarget] = useState("");
  return (
    <div className="flex items-center gap-2">
      <input
        className="input-field"
        placeholder="Category (e.g. IT)"
        value={category}
        onChange={(event) => setCategory(event.target.value)}
      />
      <input
        className="input-field"
        placeholder="Route to (e.g. risk_review)"
        value={target}
        onChange={(event) => setTarget(event.target.value)}
      />
      <button
        type="button"
        className="btn-secondary"
        disabled={!category.trim() || !target.trim()}
        onClick={() => {
          onAdd(category.trim(), target.trim());
          setCategory("");
          setTarget("");
        }}
      >
        Add
      </button>
    </div>
  );
}
