"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import { checkBudget, createBudget, extractErrorMessage, listBudgets, updateBudget } from "@/lib/api";
import type { Budget, BudgetCheckResponse, BudgetCreate, BudgetUpdate } from "@/lib/types";

const ENFORCEMENT_OPTIONS = ["hard", "soft", "none"] as const;

export default function BudgetsAdminPage() {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator";
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formState, setFormState] = useState<BudgetCreate>({
    fiscal_year: new Date().getFullYear(),
    fiscal_period: undefined,
    scope_level: "gl_account",
    scope_code: "",
    budgeted_amount: "0",
    enforcement: "soft",
  });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [checkResult, setCheckResult] = useState<BudgetCheckResponse | null>(null);
  const [checkLoading, setCheckLoading] = useState(false);

  async function loadBudgets() {
    setLoading(true);
    setError(null);
    try {
      const data = await listBudgets({ fiscal_year: formState.fiscal_year });
      setBudgets(data.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadBudgets();
  }, []);

  const selectedBudget = useMemo(() => budgets.find((item) => item.id === editingId) ?? null, [budgets, editingId]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) return;
    setSaving(true);
    setError(null);
    try {
      if (editingId && selectedBudget) {
        const payload: BudgetUpdate = {
          budgeted_amount: formState.budgeted_amount,
          enforcement: formState.enforcement,
        };
        await updateBudget(editingId, payload);
      } else {
        await createBudget(formState);
      }
      setEditingId(null);
      setFormState({
        fiscal_year: new Date().getFullYear(),
        fiscal_period: undefined,
        scope_level: "gl_account",
        scope_code: "",
        budgeted_amount: "0",
        enforcement: "soft",
      });
      await loadBudgets();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleCheck() {
    setCheckLoading(true);
    setError(null);
    try {
      const result = await checkBudget({
        requested_amount: formState.budgeted_amount,
        gl_account_code: formState.scope_level === "gl_account" ? formState.scope_code : undefined,
        cost_center: formState.scope_level === "cost_center" ? formState.scope_code : undefined,
        fiscal_year: formState.fiscal_year,
        fiscal_period: formState.fiscal_period ?? undefined,
      });
      setCheckResult(result);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setCheckLoading(false);
    }
  }

  function startEditing(item: Budget) {
    setEditingId(item.id);
    setFormState({
      fiscal_year: item.fiscal_year,
      fiscal_period: item.fiscal_period ?? undefined,
      scope_level: item.scope_level,
      scope_code: item.scope_code,
      budgeted_amount: item.budgeted_amount,
      enforcement: item.enforcement,
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Budget Rules</h2>
        <p className="mt-1 text-sm text-slate-500">
          Set tenant budgets by fiscal year, scope, and enforcement policy, then sanity-check availability live.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {!isAdmin && (
        <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          You can view the budgets list, but only administrators can create or edit budget rules.
        </p>
      )}

      <div className="card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Budget maintenance</h3>
            <p className="text-sm text-slate-500">Create a new rule or update an existing one.</p>
          </div>
          <button className="btn-secondary" onClick={() => void loadBudgets()}>
            Refresh
          </button>
        </div>

        <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="label">Fiscal year</label>
            <input
              className="input-field"
              type="number"
              value={formState.fiscal_year}
              onChange={(event) => setFormState({ ...formState, fiscal_year: Number(event.target.value) })}
            />
          </div>
          <div>
            <label className="label">Fiscal period</label>
            <input
              className="input-field"
              type="number"
              min={1}
              max={12}
              value={formState.fiscal_period ?? ""}
              onChange={(event) => setFormState({ ...formState, fiscal_period: Number(event.target.value) || undefined })}
            />
          </div>
          <div>
            <label className="label">Scope level</label>
            <select
              className="input-field"
              value={formState.scope_level}
              onChange={(event) => setFormState({ ...formState, scope_level: event.target.value })}
            >
              <option value="gl_account">GL account</option>
              <option value="cost_center">Cost center</option>
              <option value="department">Department</option>
            </select>
          </div>
          <div>
            <label className="label">Scope code</label>
            <input
              className="input-field"
              value={formState.scope_code}
              onChange={(event) => setFormState({ ...formState, scope_code: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Budgeted amount</label>
            <input
              className="input-field"
              value={formState.budgeted_amount}
              onChange={(event) => setFormState({ ...formState, budgeted_amount: event.target.value })}
            />
          </div>
          <div>
            <label className="label">Enforcement</label>
            <select
              className="input-field"
              value={formState.enforcement}
              onChange={(event) => setFormState({ ...formState, enforcement: event.target.value as BudgetCreate["enforcement"] })}
            >
              {ENFORCEMENT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2 flex gap-3">
            <button className="btn-primary" type="submit" disabled={!isAdmin || saving}>
              {saving ? "Saving..." : editingId ? "Save changes" : "Create budget"}
            </button>
            {editingId && (
              <button className="btn-secondary" type="button" onClick={() => setEditingId(null)}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Existing budgets</h3>
            <p className="text-sm text-slate-500">Current rules for the selected fiscal year.</p>
          </div>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading budgets...</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-600">
                <tr>
                  <th className="px-3 py-2">Fiscal year</th>
                  <th className="px-3 py-2">Scope</th>
                  <th className="px-3 py-2">Budget</th>
                  <th className="px-3 py-2">Enforcement</th>
                  {isAdmin && <th className="px-3 py-2">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {budgets.map((item) => (
                  <tr key={item.id} className="border-b border-slate-100">
                    <td className="px-3 py-3">{item.fiscal_year}</td>
                    <td className="px-3 py-3">{item.scope_level} / {item.scope_code}</td>
                    <td className="px-3 py-3">{item.budgeted_amount}</td>
                    <td className="px-3 py-3">{item.enforcement}</td>
                    {isAdmin && (
                      <td className="px-3 py-3">
                        <button className="btn-secondary" onClick={() => startEditing(item)}>
                          Edit
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Availability check</h3>
            <p className="text-sm text-slate-500">Test a requested value against the current budget rule.</p>
          </div>
          <button className="btn-secondary" onClick={() => void handleCheck()} disabled={checkLoading}>
            {checkLoading ? "Checking..." : "Check"}
          </button>
        </div>

        {checkResult && (
          <div className="rounded border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
            <p>Committed: {checkResult.committed}</p>
            <p>Actual: {checkResult.actual}</p>
            <p>Available: {checkResult.available ?? "n/a"}</p>
            <p className="mt-2">{checkResult.message ?? (checkResult.blocked ? "Budget blocked" : "Budget available")}</p>
          </div>
        )}
      </div>
    </div>
  );
}
