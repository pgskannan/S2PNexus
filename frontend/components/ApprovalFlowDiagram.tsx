"use client";

// Ariba-style horizontal approval flow visualization. Ported from a reference
// implementation the user built in another project (components/enterprise/
// ApprovalFlowDiagram.tsx there) -- deliberately not a graph-editor library
// (React Flow etc.): this is a purpose-built read-only stepper (avatar
// circles + connecting arrows + status colors), which is what actually
// matches SAP Ariba's look. React Flow stays reserved for the workflow
// *definition* editor (WorkflowCanvas.tsx), where free-form node editing is
// the actual point.

import React, { useState } from "react";

// ─── Public types ──────────────────────────────────────────────────────────────
export type ApprovalStepStatus = "PENDING" | "APPROVED" | "REJECTED" | "WAITING" | string;

export type ApprovalStep = {
  step_order: number;
  approver_name: string;
  approver_role?: string;
  status: ApprovalStepStatus;
  decided_at?: string;
  comment?: string;
};

type Props = {
  docNumber?: string | null;
  title?: string | null;
  steps: ApprovalStep[];
};

// ─── Helpers ───────────────────────────────────────────────────────────────────
function norm(status: ApprovalStepStatus): string {
  const s = String(status || "").toUpperCase();
  if (s === "APPROVED") return "APPROVED";
  if (s === "REJECTED") return "REJECTED";
  if (s === "WAITING") return "WAITING";
  return "PENDING";
}

function initials(name?: string) {
  return (
    (name || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?"
  );
}

function fmtDate(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

// ─── Status pill ───────────────────────────────────────────────────────────────
function StatusPill({ status }: { status: ApprovalStepStatus }) {
  const s = norm(status);
  const cfg: Record<string, { dot: string; label: string; cls: string }> = {
    APPROVED: { dot: "bg-teal-500", label: "Approved", cls: "text-teal-700" },
    PENDING: { dot: "bg-amber-500", label: "Active", cls: "text-amber-700" },
    WAITING: { dot: "bg-slate-300", label: "Waiting", cls: "text-slate-500" },
    REJECTED: { dot: "bg-red-500", label: "Rejected", cls: "text-red-700" },
  };
  const c = cfg[s] ?? { dot: "bg-slate-300", label: status, cls: "text-slate-500" };
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${c.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot} shrink-0`} />
      {c.label}
    </span>
  );
}

// ─── Connector arrow between nodes ────────────────────────────────────────────
function Connector({ status }: { status: ApprovalStepStatus }) {
  const s = norm(status);
  const color = s === "APPROVED" ? "#0d9488" : s === "PENDING" ? "#d97706" : "#cbd5e1";
  const dash = s === "PENDING" ? "5,3" : undefined;

  return (
    <div className="flex items-center shrink-0 self-center mx-1" style={{ width: 36 }}>
      <svg width="36" height="12" viewBox="0 0 36 12" fill="none" xmlns="http://www.w3.org/2000/svg">
        <line x1="0" y1="6" x2="29" y2="6" stroke={color} strokeWidth="1.8" strokeDasharray={dash} />
        <path d="M28 3 L33 6 L28 9" stroke={color} strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ─── Step card ────────────────────────────────────────────────────────────────
function StepCard({
  step,
  isSelected,
  onSelect,
}: {
  step: ApprovalStep;
  isSelected: boolean;
  onSelect: (s: ApprovalStep) => void;
}) {
  const s = norm(step.status);

  const stripeColor =
    s === "APPROVED" ? "bg-teal-500" : s === "PENDING" ? "bg-amber-400" : s === "REJECTED" ? "bg-red-400" : "bg-slate-300";

  const borderColor =
    s === "APPROVED" ? "border-teal-200" : s === "PENDING" ? "border-amber-200" : s === "REJECTED" ? "border-red-200" : "border-slate-200";

  const avatarCls = s === "APPROVED" ? "bg-teal-100 text-teal-800" : s === "PENDING" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600";

  return (
    <button
      type="button"
      onClick={() => onSelect(step)}
      className={`relative flex-shrink-0 w-[180px] rounded-xl border bg-white shadow-sm text-left
        transition-all hover:shadow-md focus:outline-none
        ${borderColor} ${isSelected ? "ring-2 ring-offset-1 ring-slate-400" : ""}`}
    >
      {/* Left colour stripe */}
      <div className={`absolute left-0 top-0 h-full w-1.5 rounded-l-xl ${stripeColor}`} />

      <div className="pl-4 pr-3 pt-2 pb-2.5">
        {/* Role label */}
        <div className="text-[8px] font-bold tracking-widest text-slate-400 uppercase mb-1.5">
          {step.approver_role?.toUpperCase() || "APPROVAL"}
        </div>

        {/* Avatar + name row */}
        <div className="flex items-center gap-2">
          <div className={`h-7 w-7 rounded-full text-[10px] font-bold flex items-center justify-center shrink-0 ${avatarCls}`}>
            {initials(step.approver_name)}
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-slate-900 truncate leading-tight">{step.approver_name}</div>
            <div className="text-[10px] text-slate-400 truncate">{step.approver_role || "Approver"}</div>
          </div>
        </div>

        {/* Status + date */}
        <div className="mt-2 flex items-center justify-between gap-2">
          <StatusPill status={step.status} />
          <span className="text-[10px] text-slate-400 whitespace-nowrap shrink-0">
            {s === "APPROVED" && step.decided_at ? fmtDate(step.decided_at) : s === "PENDING" ? "Due soon" : ""}
          </span>
        </div>
      </div>
    </button>
  );
}

// ─── Detail panel ─────────────────────────────────────────────────────────────
function DetailsPanel({ step, onClose }: { step: ApprovalStep; onClose: () => void }) {
  return (
    <div className="border-l border-slate-200 bg-slate-50 w-[220px] shrink-0 flex flex-col">
      <div className="flex items-start justify-between px-4 py-3 border-b border-slate-100">
        <div className="min-w-0">
          <div className="text-[8px] font-bold tracking-widest text-slate-400 uppercase">
            {step.approver_role?.toUpperCase() || "APPROVAL STEP"}
          </div>
          <div className="text-sm font-semibold text-slate-900 mt-0.5 truncate">{step.approver_name}</div>
          <div className="mt-1">
            <StatusPill status={step.status} />
          </div>
        </div>
        <button type="button" onClick={onClose} className="ml-2 shrink-0 text-slate-400 hover:text-slate-600 text-sm leading-none">
          ✕
        </button>
      </div>
      <div className="p-3 space-y-2 overflow-y-auto">
        {[
          { label: "Role", value: step.approver_role || "—" },
          { label: "Decided", value: step.decided_at ? new Date(step.decided_at).toLocaleString() : "—" },
          { label: "Comment", value: step.comment || "—" },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
            <div className="text-[8px] font-bold tracking-widest text-slate-400 uppercase">{label}</div>
            <div className="mt-0.5 text-[12px] text-slate-700">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Progress bar ─────────────────────────────────────────────────────────────
function ProgressBar({ steps }: { steps: ApprovalStep[] }) {
  const done = steps.filter((s) => norm(s.status) === "APPROVED").length;
  const total = steps.length || 1;
  const pct = Math.round((done / total) * 100);
  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-slate-100">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-teal-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-semibold text-slate-500 whitespace-nowrap">{pct}%</span>
    </div>
  );
}

// ─── Legend ───────────────────────────────────────────────────────────────────
function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 border-b border-slate-100 text-[10px] text-slate-500">
      {[
        { color: "bg-teal-500", label: "Approved" },
        { color: "bg-amber-500", label: "Active" },
        { color: "bg-slate-300", label: "Waiting" },
      ].map((l) => (
        <span key={l.label} className="flex items-center gap-1">
          <span className={`inline-block h-1.5 w-3 rounded-full ${l.color}`} />
          {l.label}
        </span>
      ))}
      <span className="ml-auto flex items-center gap-1 text-slate-400">
        <svg width="14" height="4" viewBox="0 0 14 4">
          <line x1="0" y1="2" x2="14" y2="2" stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4 3" />
        </svg>
        Awaiting
      </span>
    </div>
  );
}

// ─── Root component ───────────────────────────────────────────────────────────
export function ApprovalFlowDiagram({ docNumber, title, steps }: Props) {
  const [selectedStep, setSelectedStep] = useState<ApprovalStep | null>(null);

  const ordered = [...(steps || [])].sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0));
  const approvedCount = ordered.filter((s) => norm(s.status) === "APPROVED").length;

  return (
    <div className="w-full rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-3 pb-2">
        <div className="text-[8px] font-bold tracking-widest text-teal-600 uppercase">Approval Workflow</div>
        <div className="text-sm font-semibold text-slate-900 mt-0.5">
          {docNumber || "Document"}
          {title ? ` · ${title}` : ""}
        </div>
        <div className="text-[11px] text-slate-400 mt-0.5">
          {approvedCount} of {ordered.length} approvals complete
        </div>
      </div>

      <ProgressBar steps={ordered} />
      <Legend />

      {/* Flow + detail panel */}
      <div className="flex overflow-hidden">
        {/* Flow canvas */}
        <div className="flex-1 overflow-x-auto py-6 px-6">
          {ordered.length === 0 ? (
            <div className="text-[12px] text-slate-400 italic py-2">No approval steps</div>
          ) : (
            /* Pure flex row — every element sits on the same horizontal axis */
            <div className="inline-flex items-center gap-0">
              {/* Submitted pill */}
              <div className="flex-shrink-0 flex items-center gap-1.5 rounded-full border border-slate-300 bg-white px-3 py-1.5 shadow-sm">
                <span className="h-2 w-2 rounded-full bg-teal-500 shrink-0" />
                <span className="text-xs font-medium text-slate-600 whitespace-nowrap">Submitted</span>
              </div>

              {/* Steps with connectors */}
              {ordered.map((step, idx) => (
                <React.Fragment key={`${step.step_order}-${idx}`}>
                  <Connector status={step.status} />
                  <StepCard
                    step={step}
                    isSelected={selectedStep === step}
                    onSelect={(s) => setSelectedStep(selectedStep === s ? null : s)}
                  />
                </React.Fragment>
              ))}
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selectedStep && <DetailsPanel step={selectedStep} onClose={() => setSelectedStep(null)} />}
      </div>
    </div>
  );
}
