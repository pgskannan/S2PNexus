"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CheckCircle2, Sparkles, XCircle, Zap } from "lucide-react";
import type { WorkflowStepValue } from "./WorkflowCanvas";
import UserPicker from "@/components/UserPicker";
import { extractErrorMessage, generateAiText, listWorkflowFields, resolveApprovers } from "@/lib/api";
import { APPROVER_ROLE_CODES, type ResolvedApprover, type WorkflowFieldSpec } from "@/lib/types";

interface WorkflowNodeInspectorProps {
  selectedNode: WorkflowStepValue | null;
  onUpdate: (changes: Partial<WorkflowStepValue>) => void;
  /** Entity type of the definition being edited (e.g. "requisition",
   * "purchase_order") -- used to fetch the right set of condition-field
   * suggestions from GET /workflow/fields. Omit to fall back to a plain
   * text input (e.g. if the caller doesn't know the entity type yet). */
  entityType?: string;
  /** Every step in the definition being edited, in order -- used to build
   * the "go to" dropdowns for condition branches and parallel-group
   * continuation targets. Without this, those controls have nothing to list
   * and the condition-branch fields silently can't be set (the actual bug
   * reported 2026-08-02: there was no UI for on_true_next_step/
   * on_false_next_step at all). */
  allSteps?: Array<Record<string, unknown>>;
}

const STEP_END_LABEL = "End workflow (approved)";
const END_VALUE = "__end__";

function StepTargetSelect({
  value,
  allSteps,
  excludeIndex,
  onChange,
}: {
  value: number | null | undefined;
  allSteps: Array<Record<string, unknown>>;
  excludeIndex?: number;
  onChange: (index: number | null) => void;
}) {
  // "End workflow" is persisted as allSteps.length (an index past the last
  // step). Treat any stored value >= the current step count as End so the
  // select never shows stale/blank when steps are added after "End" is set.
  const isEnd = value != null && (value as number) >= allSteps.length;
  const selectValue = value == null ? "" : isEnd ? END_VALUE : String(value);
  return (
    <select
      className="input-field"
      value={selectValue}
      onChange={(event) => {
        const next = event.target.value;
        if (next === "") onChange(null);
        else if (next === END_VALUE) onChange(allSteps.length);
        else onChange(Number(next));
      }}
    >
      <option value="">Select a step...</option>
      {allSteps.map((step, index) => {
        if (index === excludeIndex) return null;
        const label = String(step.name || `Step ${index + 1}`);
        const type = String(step.step_type || "approval");
        return (
          <option key={index} value={index}>
            {index}: {label} ({type})
          </option>
        );
      })}
      <option value={END_VALUE}>{STEP_END_LABEL}</option>
    </select>
  );
}

function ConditionFieldInput({
  value,
  entityType,
  onChange,
}: {
  value: string;
  entityType?: string;
  onChange: (field: string) => void;
}) {
  const [options, setOptions] = useState<WorkflowFieldSpec[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!entityType) {
      setOptions([]);
      return;
    }
    listWorkflowFields(entityType)
      .then((res) => {
        if (!cancelled) setOptions(res.fields);
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [entityType]);

  const suggestions = useMemo(() => {
    const query = value.trim().toLowerCase();
    const matches = query
      ? options.filter(
          (option) => option.path.toLowerCase().includes(query) || option.label.toLowerCase().includes(query)
        )
      : options;
    return matches.slice(0, 20);
  }, [options, value]);

  return (
    <div className="relative">
      <input
        className="input-field"
        value={value}
        placeholder={entityType ? "Start typing to search fields..." : "e.g. estimated_value"}
        onFocus={() => setOpen(true)}
        onChange={(event) => onChange(event.target.value)}
        onBlur={() => {
          // Delay so a click on a suggestion registers before the list unmounts.
          setTimeout(() => setOpen(false), 150);
        }}
      />
      {open && entityType && suggestions.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {suggestions.map((option) => (
            <li key={option.path}>
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
                onMouseDown={(event) => {
                  // onMouseDown fires before the input's onBlur, so the click
                  // registers instead of being swallowed by the blur timeout.
                  event.preventDefault();
                  onChange(option.path);
                  setOpen(false);
                }}
              >
                <span>
                  <span className="font-mono text-slate-700">{option.path}</span>
                  <span className="ml-2 text-slate-400">{option.label}</span>
                </span>
                <span className="badge bg-slate-100 text-slate-500">{option.type}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && entityType && suggestions.length === 0 && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-400 shadow-lg">
          No matching fields for this document type -- you can still type a custom field name.
        </div>
      )}
    </div>
  );
}

/** Optional "run this step alongside other steps, concurrently" control for
 * approval/notification/auto steps (the only step types a parallel_group can
 * contain -- see schemas/workflow.py's PARALLEL_GROUP_MEMBER_TYPES). Give
 * two or more steps the same group name and they all activate together; the
 * workflow only advances once every approval-type member is satisfied. */
function ParallelGroupFields({
  selectedNode,
  allSteps,
  selfIndex,
  onUpdate,
}: {
  selectedNode: WorkflowStepValue;
  allSteps: Array<Record<string, unknown>>;
  selfIndex?: number;
  onUpdate: (changes: Partial<WorkflowStepValue>) => void;
}) {
  const siblingCount = allSteps.filter(
    (step, index) => index !== selfIndex && step.parallel_group === selectedNode.parallel_group
  ).length;

  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <label className="label">Parallel group (optional)</label>
      <input
        className="input-field"
        placeholder="e.g. finance_legal_review"
        value={selectedNode.parallel_group || ""}
        onChange={(event) => onUpdate({ parallel_group: event.target.value || undefined })}
      />
      <p className="mt-1 text-xs text-slate-500">
        Give two or more approval/notification/auto steps the same group name to run them at the same time -- the
        workflow only continues once every approval step in the group is satisfied (a rejection in any of them
        rejects the whole workflow, same as a single-step rejection).
      </p>
      {selectedNode.parallel_group && (
        <>
          <p className="mt-2 text-xs text-slate-600">
            {siblingCount > 0
              ? `${siblingCount + 1} step(s) share this group.`
              : "No other step uses this group name yet -- add it to at least one more step to actually run in parallel."}
          </p>
          <label className="label mt-2">Continue to (after the group completes)</label>
          <StepTargetSelect
            value={selectedNode.parallel_next_step}
            allSteps={allSteps}
            excludeIndex={selfIndex}
            onChange={(index) => onUpdate({ parallel_next_step: index })}
          />
          <p className="mt-1 text-xs text-slate-500">
            Every step in the same group must point to the same target -- setting it here updates just this step, so
            set it consistently on each member.
          </p>
        </>
      )}
    </div>
  );
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

const STEP_TYPE_META: Record<string, { label: string; badgeClass: string }> = {
  condition: { label: "Condition", badgeClass: "bg-violet-100 text-violet-700" },
  approval: { label: "Approval", badgeClass: "bg-amber-100 text-amber-700" },
  notification: { label: "Notification", badgeClass: "bg-teal-100 text-teal-700" },
  auto: { label: "Auto", badgeClass: "bg-green-100 text-green-700" },
  ai: { label: "AI rule", badgeClass: "bg-cyan-100 text-cyan-700" },
  end: { label: "End", badgeClass: "bg-red-100 text-red-700" },
};

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h4 className="text-sm font-semibold text-slate-700">{title}</h4>
      {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      <div className="mt-3 space-y-3">{children}</div>
    </div>
  );
}

export function WorkflowNodeInspector({ selectedNode, onUpdate, entityType, allSteps = [] }: WorkflowNodeInspectorProps) {
  const [previewAmount, setPreviewAmount] = useState("");
  const [escalateRole, setEscalateRole] = useState("");
  const [escalateResolvedName, setEscalateResolvedName] = useState<string | null>(null);
  const [generatingReason, setGeneratingReason] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);

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

  async function handleGenerateReason() {
    if (!selectedNode) return;
    setGeneratingReason(true);
    setReasonError(null);
    try {
      const approver = selectedNode.role_code
        ? `role ${selectedNode.role_code} (resolved via the approver matrix)`
        : selectedNode.approvers?.length
        ? `${selectedNode.approvers.length} named approver(s)`
        : "unassigned";
      const prevStep = selfIndex !== undefined && selfIndex > 0 ? allSteps[selfIndex - 1] : null;
      const routeContext =
        prevStep && String(prevStep.step_type) === "condition"
          ? ` This step is reached via the "${String(prevStep.name || "condition")}" rule (${String(prevStep.field || "")} ${String(prevStep.operator || "")} ${String(prevStep.value ?? "")}).`
          : "";
      const prompt =
        `Draft a short, professional "reason for this approval" (1-2 sentences) that an approver will see as a ` +
        `hover tooltip on this approval step in a procurement workflow designer.\n\n` +
        `- Step name: ${selectedNode.name}\n` +
        `- Approver: ${approver}\n` +
        `- Required approvals: ${selectedNode.required_approvals ?? 1}\n` +
        `- Escalates after: ${selectedNode.escalate_after_hours ? `${selectedNode.escalate_after_hours}h` : "not set"}\n` +
        `- Document type: ${entityType ?? "unknown"}${routeContext}\n\n` +
        `Return only the reason text -- no quotes, no prefixes.`;
      const text = await generateAiText(
        prompt,
        "You are a concise procurement workflow designer. Reply with 1-2 sentences only."
      );
      if (text) onUpdate({ reason: text.trim() });
    } catch (err) {
      setReasonError(extractErrorMessage(err));
    } finally {
      setGeneratingReason(false);
    }
  }

  const selfIndex = selectedNode.id.startsWith("step-") ? Number(selectedNode.id.slice("step-".length)) : undefined;
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
      {/* Header: type badge + editable step name */}
      <div className="flex flex-wrap items-center gap-3">
        <span className={`badge ${STEP_TYPE_META[selectedNode.step_type]?.badgeClass ?? "bg-slate-100 text-slate-600"}`}>
          {STEP_TYPE_META[selectedNode.step_type]?.label ?? selectedNode.step_type}
        </span>
        <input
          className="input-field min-w-[220px] flex-1 font-medium"
          value={selectedNode.name}
          onChange={(event) => onUpdate({ name: event.target.value })}
          placeholder="Step name"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {selectedNode.step_type === "condition" && (
          <>
            <Section
              title="Rule"
              description="Evaluated when the workflow reaches this step, then routed down the Yes or No path."
            >
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-violet-100 px-2 py-1 text-xs font-bold uppercase tracking-wide text-violet-700">
                    IF
                  </span>
                  <ConditionFieldInput
                    value={selectedNode.field || ""}
                    entityType={entityType}
                    onChange={(field) => onUpdate({ field })}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
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
                  <input
                    className="input-field"
                    value={typeof selectedNode.value === "string" ? selectedNode.value : ""}
                    placeholder="Compare value"
                    onChange={(event) => onUpdate({ value: event.target.value })}
                  />
                </div>
              </div>
            </Section>
            <Section
              title="Branch routing"
              description="Both branches must be set to save. Choose “End workflow (approved)” if an outcome should finish instead of continuing."
            >
              <div className="rounded-md border border-green-200 bg-green-50 p-3">
                <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-green-700">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Yes — when the rule is true
                </label>
                <div className="mt-2">
                  <StepTargetSelect
                    value={selectedNode.on_true_next_step}
                    allSteps={allSteps}
                    excludeIndex={selfIndex}
                    onChange={(index) => onUpdate({ on_true_next_step: index })}
                  />
                </div>
              </div>
              <div className="rounded-md border border-red-200 bg-red-50 p-3">
                <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-red-700">
                  <XCircle className="h-3.5 w-3.5" />
                  No — when the rule is false
                </label>
                <div className="mt-2">
                  <StepTargetSelect
                    value={selectedNode.on_false_next_step}
                    allSteps={allSteps}
                    excludeIndex={selfIndex}
                    onChange={(index) => onUpdate({ on_false_next_step: index })}
                  />
                </div>
              </div>
            </Section>
          </>
        )}

        {selectedNode.step_type === "approval" && (
          <>
            <Section
              title="Who approves"
              description="Pick named users, or resolve a role through the approver matrix."
            >
              <div>
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
            </Section>
            <Section
              title="Reason for this approval"
              description="A short explanation shown to approvers as a hover tooltip on this step."
            >
              <textarea
                className="input-field"
                rows={3}
                placeholder="e.g. Verify the spend is within budget before the PO is created."
                value={selectedNode.reason || ""}
                onChange={(event) => onUpdate({ reason: event.target.value || undefined })}
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={generatingReason}
                  onClick={() => void handleGenerateReason()}
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {generatingReason ? "Drafting…" : "AI-draft reason"}
                </button>
                {reasonError && <span className="text-xs text-red-600">{reasonError}</span>}
              </div>
            </Section>
            <Section
              title="Continue after approval"
              description="Where to go once this approval is satisfied. For Yes/No condition arms, choose End (or a shared merge step) — never the other arm."
            >
              <StepTargetSelect
                value={selectedNode.next_step}
                allSteps={allSteps}
                excludeIndex={selfIndex}
                onChange={(index) => onUpdate({ next_step: index })}
              />
            </Section>
            <Section
              title="Approval behavior"
              description="How many approvals are needed and what happens when a task is ignored."
            >
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
                  If an SLA definition exists for this document type and role, the SLA target takes precedence at runtime.
                </p>
              </div>
            </Section>
            <Section
              title="Escalation target"
              description="Who takes over when the step is escalated."
            >
              <div>
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
            </Section>
            <Section
              title="Parallel branches"
              description="Give two or more steps the same group to run them at the same time."
            >
              <ParallelGroupFields selectedNode={selectedNode} allSteps={allSteps} selfIndex={selfIndex} onUpdate={onUpdate} />
            </Section>
          </>
        )}

        {selectedNode.step_type === "auto" && (
          <>
            <Section
              title="Auto-approval"
              description="This step approves automatically and records an AUTO_APPROVED audit event. No configuration needed beyond the step name."
            >
              <div className="flex items-center gap-2 rounded-md bg-green-50 p-3 text-sm text-green-700">
                <Zap className="h-4 w-4" />
                <span>This step approves itself automatically.</span>
              </div>
            </Section>
            <Section title="Parallel branches" description="Run this step alongside other steps in the same group.">
              <ParallelGroupFields selectedNode={selectedNode} allSteps={allSteps} selfIndex={selfIndex} onUpdate={onUpdate} />
            </Section>
          </>
        )}

        {selectedNode.step_type === "ai" && (
          <>
            <Section
              title="AI decision rules"
              description="How the AI agent decides before this step lets a document through."
            >
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
            </Section>
            <Section
              title="Category routing"
              description="Routes documents in a category to a named node (e.g. IT → risk_review)."
            >
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
            </Section>
          </>
        )}

        {selectedNode.step_type === "notification" && (
          <>
            <Section title="Recipients" description="Who receives this notification.">
              <UserPicker
                value={selectedNode.recipients || []}
                onChange={(ids) => onUpdate({ recipients: ids })}
                multiple
              />
            </Section>
            <Section title="Message" description="The notification body. You can use {context} placeholders.">
              <textarea
                className="input-field"
                rows={4}
                value={selectedNode.message_template || ""}
                onChange={(event) => onUpdate({ message_template: event.target.value })}
              />
            </Section>
            <Section title="Parallel branches" description="Run this step alongside other steps in the same group.">
              <ParallelGroupFields selectedNode={selectedNode} allSteps={allSteps} selfIndex={selfIndex} onUpdate={onUpdate} />
            </Section>
          </>
        )}
      </div>
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
