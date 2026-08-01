"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import {
  createSlaDefinition,
  deactivateApproverSeed,
  extractErrorMessage,
  getApprovalAnalytics,
  listApproverSeeds,
  listSlaDefinitions,
  updateApproverSeed,
  upsertApproverSeed,
} from "@/lib/api";
import {
  APPROVER_ROLE_CODES,
  type ApprovalAnalytics,
  type ApproverSeed,
  type ApproverSeedUpsert,
  type SlaDefinitionEntry,
} from "@/lib/types";
import UserPicker from "@/components/UserPicker";

const EMPTY_FORM: ApproverSeedUpsert = {
  user_id: "",
  role_code: APPROVER_ROLE_CODES[0],
  display_name: "",
  email: "",
  org_unit_id: "",
  approval_limit_currency: "USD",
  approval_limit_amount: "",
  category_scope: "",
  supplier_scope: "",
  is_primary_approver: true,
  active_flag: true,
};

export default function ApprovalsAdminPage() {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator";
  const [tab, setTab] = useState<"matrix" | "sla">("matrix");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Dynamic Approvals</h2>
        <p className="mt-1 text-sm text-slate-500">
          One place to control who approves what: the approver matrix (role, limits, scope, delegation) and the SLA
          targets that drive escalation.
        </p>
      </div>

      {!isAdmin && (
        <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          You can view the approval matrix and SLA targets, but only administrators can edit them.
        </p>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button className={tab === "matrix" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("matrix")}>
          Approver Matrix
        </button>
        <button className={tab === "sla" ? "btn-primary" : "btn-secondary"} onClick={() => setTab("sla")}>
          SLA Targets
        </button>
      </div>

      {tab === "matrix" ? (
        <ApproverMatrixTab isAdmin={isAdmin} onError={setError} />
      ) : (
        <SlaTargetsTab isAdmin={isAdmin} onError={setError} />
      )}
    </div>
  );
}

function ApproverMatrixTab({ isAdmin, onError }: { isAdmin: boolean; onError: (message: string | null) => void }) {
  const [seeds, setSeeds] = useState<ApproverSeed[]>([]);
  const [loading, setLoading] = useState(true);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [formState, setFormState] = useState<ApproverSeedUpsert>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    onError(null);
    try {
      const data = await listApproverSeeds({ include_inactive: includeInactive, limit: 500 });
      setSeeds(data.items);
    } catch (err) {
      onError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [includeInactive]);

  function startEditing(seed: ApproverSeed) {
    setEditingId(seed.id);
    setFormState({
      user_id: seed.user_id,
      role_code: seed.role_code,
      display_name: seed.display_name,
      email: seed.email,
      org_unit_id: seed.org_unit_id ?? "",
      approval_limit_currency: seed.approval_limit_currency ?? "USD",
      approval_limit_amount: seed.approval_limit_amount ?? "",
      category_scope: seed.category_scope ?? "",
      supplier_scope: seed.supplier_scope ?? "",
      is_primary_approver: seed.is_primary_approver,
      backup_approver_user_id: seed.backup_approver_user_id ?? undefined,
      delegation_start_date: seed.delegation_start_date ?? undefined,
      delegation_end_date: seed.delegation_end_date ?? undefined,
      active_flag: seed.active_flag,
    });
  }

  function resetForm() {
    setEditingId(null);
    setFormState(EMPTY_FORM);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) return;
    setSaving(true);
    onError(null);
    try {
      const payload: ApproverSeedUpsert = {
        ...formState,
        approval_limit_amount: formState.approval_limit_amount || null,
        org_unit_id: formState.org_unit_id || null,
        category_scope: formState.category_scope || null,
        supplier_scope: formState.supplier_scope || null,
        delegation_start_date: formState.delegation_start_date || null,
        delegation_end_date: formState.delegation_end_date || null,
      };
      if (editingId) {
        // user_id/role_code are the upsert key -- the PATCH endpoint rejects
        // changes to them, so send everything else.
        const { user_id, role_code, ...rest } = payload;
        await updateApproverSeed(editingId, rest);
      } else {
        if (!payload.user_id) {
          onError("Pick a user for this approver seed.");
          setSaving(false);
          return;
        }
        await upsertApproverSeed(payload);
      }
      resetForm();
      await load();
    } catch (err) {
      onError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(seed: ApproverSeed) {
    if (!isAdmin) return;
    if (!window.confirm(`Deactivate ${seed.display_name} as ${seed.role_code}? Historical audit records are kept.`)) {
      return;
    }
    onError(null);
    try {
      await deactivateApproverSeed(seed.id);
      await load();
    } catch (err) {
      onError(extractErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      {isAdmin && (
        <div className="card space-y-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">
              {editingId ? "Edit approver" : "Add approver to matrix"}
            </h3>
            <p className="text-sm text-slate-500">
              Role + limits + scope decide who a &quot;By role&quot; workflow step resolves to at runtime.
            </p>
          </div>
          <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-2">
            {!editingId && (
              <div>
                <label className="label">User</label>
                <UserPicker
                  value={formState.user_id ? [formState.user_id] : []}
                  onChange={(ids) => setFormState({ ...formState, user_id: ids[0] ?? "" })}
                  multiple={false}
                />
              </div>
            )}
            <div>
              <label className="label">Role</label>
              <select
                className="input-field"
                value={formState.role_code}
                disabled={Boolean(editingId)}
                onChange={(event) => setFormState({ ...formState, role_code: event.target.value })}
              >
                {APPROVER_ROLE_CODES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Display name</label>
              <input
                className="input-field"
                value={formState.display_name ?? ""}
                onChange={(event) => setFormState({ ...formState, display_name: event.target.value })}
              />
            </div>
            <div>
              <label className="label">Email</label>
              <input
                className="input-field"
                type="email"
                value={formState.email ?? ""}
                onChange={(event) => setFormState({ ...formState, email: event.target.value })}
              />
            </div>
            <div>
              <label className="label">Org unit</label>
              <input
                className="input-field"
                value={formState.org_unit_id ?? ""}
                onChange={(event) => setFormState({ ...formState, org_unit_id: event.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label">Approval limit</label>
                <input
                  className="input-field"
                  type="number"
                  min={0}
                  placeholder="No ceiling"
                  value={formState.approval_limit_amount ?? ""}
                  onChange={(event) => setFormState({ ...formState, approval_limit_amount: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Currency</label>
                <input
                  className="input-field"
                  maxLength={3}
                  value={formState.approval_limit_currency ?? ""}
                  onChange={(event) => setFormState({ ...formState, approval_limit_currency: event.target.value.toUpperCase() })}
                />
              </div>
            </div>
            <div>
              <label className="label">Category scope (comma-separated, empty = all)</label>
              <input
                className="input-field"
                placeholder="IT, MRO"
                value={formState.category_scope ?? ""}
                onChange={(event) => setFormState({ ...formState, category_scope: event.target.value })}
              />
            </div>
            <div>
              <label className="label">Supplier scope (comma-separated IDs, empty = all)</label>
              <input
                className="input-field"
                value={formState.supplier_scope ?? ""}
                onChange={(event) => setFormState({ ...formState, supplier_scope: event.target.value })}
              />
            </div>
            <div>
              <label className="label">Backup approver</label>
              <UserPicker
                value={formState.backup_approver_user_id ? [formState.backup_approver_user_id] : []}
                onChange={(ids) => setFormState({ ...formState, backup_approver_user_id: ids[0] ?? undefined })}
                multiple={false}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label">Delegation start</label>
                <input
                  className="input-field"
                  type="date"
                  value={formState.delegation_start_date ?? ""}
                  onChange={(event) => setFormState({ ...formState, delegation_start_date: event.target.value })}
                />
              </div>
              <div>
                <label className="label">Delegation end</label>
                <input
                  className="input-field"
                  type="date"
                  value={formState.delegation_end_date ?? ""}
                  onChange={(event) => setFormState({ ...formState, delegation_end_date: event.target.value })}
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input
                id="is-primary"
                type="checkbox"
                checked={Boolean(formState.is_primary_approver)}
                onChange={(event) => setFormState({ ...formState, is_primary_approver: event.target.checked })}
              />
              <label htmlFor="is-primary" className="text-sm text-slate-700">
                Primary approver for this role
              </label>
            </div>
            <div className="md:col-span-2 flex gap-3">
              <button className="btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving..." : editingId ? "Save changes" : "Add to matrix"}
              </button>
              {editingId && (
                <button className="btn-secondary" type="button" onClick={resetForm}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      <div className="card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Approver matrix</h3>
            <p className="text-sm text-slate-500">Everyone a role-based workflow step can resolve to.</p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(event) => setIncludeInactive(event.target.checked)}
              />
              Show inactive
            </label>
            <button className="btn-secondary" onClick={() => void load()}>
              Refresh
            </button>
          </div>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading approver matrix...</p>
        ) : seeds.length === 0 ? (
          <p className="text-sm text-slate-500">
            No approver seeds yet. Add one above, or run backend/scripts/seed_approver_matrix.py for a demo ladder.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-600">
                <tr>
                  <th className="px-3 py-2">Approver</th>
                  <th className="px-3 py-2">Role</th>
                  <th className="px-3 py-2">Org unit</th>
                  <th className="px-3 py-2">Limit</th>
                  <th className="px-3 py-2">Category scope</th>
                  <th className="px-3 py-2">Primary</th>
                  <th className="px-3 py-2">Delegation window</th>
                  <th className="px-3 py-2">Active</th>
                  {isAdmin && <th className="px-3 py-2">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {seeds.map((seed) => (
                  <tr key={seed.id} className={`border-b border-slate-100 ${seed.active_flag ? "" : "opacity-50"}`}>
                    <td className="px-3 py-3">
                      <div className="font-medium text-slate-800">{seed.display_name}</div>
                      <div className="text-xs text-slate-500">{seed.email}</div>
                    </td>
                    <td className="px-3 py-3">{seed.role_code}</td>
                    <td className="px-3 py-3">{seed.org_unit_id || "—"}</td>
                    <td className="px-3 py-3">
                      {seed.approval_limit_amount
                        ? `${seed.approval_limit_currency || ""} ${seed.approval_limit_amount}`
                        : "No ceiling"}
                    </td>
                    <td className="px-3 py-3">{seed.category_scope || "All"}</td>
                    <td className="px-3 py-3">{seed.is_primary_approver ? "Yes" : "No"}</td>
                    <td className="px-3 py-3">
                      {seed.delegation_start_date || seed.delegation_end_date
                        ? `${seed.delegation_start_date ?? "…"} → ${seed.delegation_end_date ?? "…"}`
                        : "—"}
                    </td>
                    <td className="px-3 py-3">{seed.active_flag ? "Active" : "Inactive"}</td>
                    {isAdmin && (
                      <td className="px-3 py-3">
                        <div className="flex gap-2">
                          <button className="btn-secondary" onClick={() => startEditing(seed)}>
                            Edit
                          </button>
                          {seed.active_flag && (
                            <button className="btn-secondary" onClick={() => void handleDeactivate(seed)}>
                              Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

const SLA_DOCUMENT_TYPES = ["requisition", "purchase_order", "goods_receipt", "invoice_exception", "supplier"];

function SlaTargetsTab({ isAdmin, onError }: { isAdmin: boolean; onError: (message: string | null) => void }) {
  const [definitions, setDefinitions] = useState<SlaDefinitionEntry[]>([]);
  const [analytics, setAnalytics] = useState<ApprovalAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formState, setFormState] = useState({
    document_type: SLA_DOCUMENT_TYPES[0],
    role_code: "",
    target_duration_minutes: 1440,
    severity: "WARNING",
  });

  async function load() {
    setLoading(true);
    onError(null);
    try {
      const [defs, stats] = await Promise.all([listSlaDefinitions({ limit: 500 }), getApprovalAnalytics()]);
      setDefinitions(defs.items);
      setAnalytics(stats);
    } catch (err) {
      onError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function breachRateFor(nodeKey: string | null | undefined): string {
    if (!analytics || !nodeKey) return "—";
    const row = analytics.sla_breach_rate_by_node.find((r) => r.node === nodeKey);
    return row ? `${row.breach_rate}% of ${row.total}` : "—";
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) return;
    setSaving(true);
    onError(null);
    try {
      await createSlaDefinition({
        document_type: formState.document_type,
        role_code: formState.role_code || undefined,
        target_duration_minutes: formState.target_duration_minutes,
        severity: formState.severity,
      });
      await load();
    } catch (err) {
      onError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      {isAdmin && (
        <div className="card space-y-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Add SLA target</h3>
            <p className="text-sm text-slate-500">
              Sets the approval deadline per document type (optionally per role). Tasks past the target feed the
              escalation sweep and the breach numbers below.
            </p>
          </div>
          <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-4">
            <div>
              <label className="label">Document type</label>
              <select
                className="input-field"
                value={formState.document_type}
                onChange={(event) => setFormState({ ...formState, document_type: event.target.value })}
              >
                {SLA_DOCUMENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Role (optional)</label>
              <select
                className="input-field"
                value={formState.role_code}
                onChange={(event) => setFormState({ ...formState, role_code: event.target.value })}
              >
                <option value="">Any role</option>
                {APPROVER_ROLE_CODES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Target (minutes)</label>
              <input
                className="input-field"
                type="number"
                min={1}
                value={formState.target_duration_minutes}
                onChange={(event) => setFormState({ ...formState, target_duration_minutes: Number(event.target.value) })}
              />
            </div>
            <div>
              <label className="label">Severity</label>
              <select
                className="input-field"
                value={formState.severity}
                onChange={(event) => setFormState({ ...formState, severity: event.target.value })}
              >
                <option value="WARNING">WARNING</option>
                <option value="CRITICAL">CRITICAL</option>
              </select>
            </div>
            <div className="md:col-span-4">
              <button className="btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving..." : "Add SLA target"}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">SLA targets</h3>
            <p className="text-sm text-slate-500">
              {analytics
                ? `${analytics.total_sla_breaches} breaches across ${analytics.total_sla_metrics} measured approvals.`
                : "Targets currently driving approval deadlines."}
            </p>
          </div>
          <button className="btn-secondary" onClick={() => void load()}>
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading SLA targets...</p>
        ) : definitions.length === 0 ? (
          <p className="text-sm text-slate-500">
            No SLA targets configured. Approval steps fall back to their per-step escalate-after-hours value.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-600">
                <tr>
                  <th className="px-3 py-2">Document type</th>
                  <th className="px-3 py-2">Role</th>
                  <th className="px-3 py-2">Target</th>
                  <th className="px-3 py-2">Severity</th>
                  <th className="px-3 py-2">Breach rate (by node)</th>
                </tr>
              </thead>
              <tbody>
                {definitions.map((definition) => (
                  <tr key={definition.id} className="border-b border-slate-100">
                    <td className="px-3 py-3">{definition.document_type}</td>
                    <td className="px-3 py-3">{definition.role_code || definition.node_type || "Any"}</td>
                    <td className="px-3 py-3">
                      {definition.target_duration_minutes >= 60
                        ? `${Math.round((definition.target_duration_minutes / 60) * 10) / 10}h`
                        : `${definition.target_duration_minutes}m`}
                    </td>
                    <td className="px-3 py-3">{definition.severity}</td>
                    <td className="px-3 py-3">{breachRateFor(definition.role_code)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
