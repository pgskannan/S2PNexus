"use client";

/**
 * Supplier Type configuration matrix admin (FS Sections 4 + 17).
 * Changing registration_mode here changes next-request behavior without a deploy.
 */

import { useEffect, useMemo, useState } from "react";
import { usePagination } from "@/components/Pagination";
import Pagination from "@/components/Pagination";
import {
  createSupplierType,
  deactivateSupplierType,
  extractErrorMessage,
  listSupplierTypes,
  updateSupplierType,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { RegistrationMode, SupplierType, SupplierTypeInput } from "@/lib/types";

const MODULE_OPTIONS = ["core", "tax", "bank", "compliance", "esg", "infosec", "financial"] as const;
const MODE_OPTIONS: RegistrationMode[] = ["auto", "manual", "none"];

const emptyForm = (): SupplierTypeInput => ({
  code: "",
  name: "",
  registration_mode: "manual",
  registration_method: "excel_only",
  required_questionnaire_modules: ["core", "tax", "bank", "compliance"],
  approval_workflow_config: ["BU_MANAGER", "PROC_HEAD"],
  ad_hoc_task_templates: [],
  notification_rule: { sla_days: 14, reminder_at_days: [7, 11], escalation_at_days: 14 },
  description: "",
  is_active: true,
});

export default function SupplierTypesAdminPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "administrator";

  const [rows, setRows] = useState<SupplierType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<SupplierType | null>(null);
  const [form, setForm] = useState<SupplierTypeInput>(emptyForm());
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);

  const { pageItems, page, setPage, totalPages, pageSize } = usePagination(rows, 10);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listSupplierTypes({ limit: 500 });
      setRows(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const moduleLabel = useMemo(
    () => (mods: string[]) => (mods.length ? mods.join(", ") : "—"),
    []
  );

  function openCreate() {
    setEditing(null);
    setForm(emptyForm());
    setShowForm(true);
  }

  function openEdit(row: SupplierType) {
    setEditing(row);
    setForm({
      code: row.code,
      name: row.name,
      registration_mode: row.registration_mode as RegistrationMode,
      registration_method: row.registration_method || "excel_only",
      required_questionnaire_modules: [...row.required_questionnaire_modules],
      approval_workflow_config: [...row.approval_workflow_config],
      ad_hoc_task_templates: row.ad_hoc_task_templates || [],
      notification_rule: row.notification_rule || {},
      qualification_rule: row.qualification_rule,
      preferred_supplier_rule: row.preferred_supplier_rule,
      description: row.description || "",
      is_active: row.is_active,
    });
    setShowForm(true);
  }

  function toggleModule(code: string) {
    const current = form.required_questionnaire_modules || [];
    const next = current.includes(code)
      ? current.filter((c) => c !== code)
      : [...current, code];
    setForm({ ...form, required_questionnaire_modules: next });
  }

  async function save() {
    if (!isAdmin) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (editing) {
        const { code: _code, ...patch } = form;
        await updateSupplierType(editing.id, patch);
        setNotice(`Updated ${editing.code}.`);
      } else {
        await createSupplierType(form);
        setNotice(`Created ${form.code}.`);
      }
      setShowForm(false);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function deactivate(row: SupplierType) {
    if (!isAdmin) return;
    setBusy(true);
    setError(null);
    try {
      await deactivateSupplierType(row.id);
      setNotice(`Deactivated ${row.code}.`);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Supplier Types</h1>
          <p className="mt-1 text-sm text-slate-500">
            Configuration matrix for registration mode, questionnaire modules, and approval chains.
          </p>
        </div>
        {isAdmin && (
          <button type="button" className="btn-primary" onClick={openCreate} disabled={busy}>
            New type
          </button>
        )}
      </div>

      {!isAdmin && (
        <div className="card border border-amber-200 bg-amber-50 text-sm text-amber-800">
          Read-only view — administrator role required to edit supplier types.
        </div>
      )}
      {error && <div className="card border border-red-200 bg-red-50 text-sm text-red-700">{error}</div>}
      {notice && <div className="card border border-green-200 bg-green-50 text-sm text-green-700">{notice}</div>}

      <div className="card overflow-x-auto">
        {loading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          <>
            <table className="min-w-full text-left text-sm">
              <thead className="border-b text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Code</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Mode</th>
                  <th className="py-2 pr-4">Modules</th>
                  <th className="py-2 pr-4">Approvals</th>
                  <th className="py-2 pr-4">Active</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100">
                    <td className="py-2 pr-4 font-mono text-xs">{row.code}</td>
                    <td className="py-2 pr-4">{row.name}</td>
                    <td className="py-2 pr-4 uppercase">{row.registration_mode}</td>
                    <td className="py-2 pr-4 text-xs text-slate-600">
                      {moduleLabel(row.required_questionnaire_modules)}
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-600">
                      {row.approval_workflow_config.join(" → ") || "—"}
                    </td>
                    <td className="py-2 pr-4">{row.is_active ? "Yes" : "No"}</td>
                    <td className="py-2 space-x-2">
                      <button
                        type="button"
                        className="btn-secondary text-xs"
                        onClick={() => openEdit(row)}
                        disabled={!isAdmin || busy}
                      >
                        Edit
                      </button>
                      {row.is_active && (
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          onClick={() => void deactivate(row)}
                          disabled={!isAdmin || busy}
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {!pageItems.length && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-slate-500">
                      No supplier types yet. Run{" "}
                      <code className="text-xs">python -m scripts.seed_supplier_types</code>.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <Pagination
              page={page}
              totalPages={totalPages}
              totalItems={rows.length}
              pageSize={pageSize}
              onPageChange={setPage}
            />
          </>
        )}
      </div>

      {showForm && (
        <div className="card space-y-4">
          <h2 className="text-lg font-medium">{editing ? `Edit ${editing.code}` : "New supplier type"}</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label" htmlFor="code">
                Code
              </label>
              <input
                id="code"
                className="input-field"
                disabled={!!editing}
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
              />
            </div>
            <div>
              <label className="label" htmlFor="name">
                Name
              </label>
              <input
                id="name"
                className="input-field"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor="mode">
                Registration mode
              </label>
              <select
                id="mode"
                className="input-field"
                value={form.registration_mode}
                onChange={(e) =>
                  setForm({ ...form, registration_mode: e.target.value as RegistrationMode })
                }
              >
                {MODE_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {m.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="approvals">
                Approval chain (comma-separated role codes)
              </label>
              <input
                id="approvals"
                className="input-field"
                value={(form.approval_workflow_config || []).join(", ")}
                onChange={(e) =>
                  setForm({
                    ...form,
                    approval_workflow_config: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
              />
            </div>
          </div>
          <div>
            <span className="label">Required questionnaire modules</span>
            <div className="mt-2 flex flex-wrap gap-3">
              {MODULE_OPTIONS.map((code) => (
                <label key={code} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={(form.required_questionnaire_modules || []).includes(code)}
                    onChange={() => toggleModule(code)}
                  />
                  {code}
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="label" htmlFor="desc">
              Description
            </label>
            <textarea
              id="desc"
              className="input-field"
              rows={2}
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn-primary" disabled={busy} onClick={() => void save()}>
              Save
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => setShowForm(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
