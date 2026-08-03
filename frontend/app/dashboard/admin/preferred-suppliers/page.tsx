"use client";

/**
 * Preferred Supplier Management console (Template Framework Phase 5).
 *
 * Lists every computed PreferredSupplierStatus with the four-component
 * breakdown behind the composite (spec Section 17), filters, an explicit
 * recompute trigger (the only trigger in this batch -- no on-change hooks),
 * a qualification quick-set (the Phase 2 placeholder input), and a manual
 * override control. Overrides require a reason and route through the
 * preferred_supplier_review approval chain when one is configured.
 */

import { useEffect, useMemo, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import {
  extractErrorMessage,
  listPreferredStatuses,
  listSuppliers,
  overridePreferredStatus,
  recomputeAllPreferredStatuses,
  recomputePreferredStatus,
  upsertSupplierQualification,
} from "@/lib/api";
import type { PreferredSupplierStatus, Supplier } from "@/lib/types";

const STATUS_OPTIONS = ["strategic", "preferred", "approved", "blocked", "none"] as const;

const statusColors: Record<string, string> = {
  strategic: "bg-purple-100 text-purple-700",
  preferred: "bg-green-100 text-green-700",
  approved: "bg-blue-100 text-blue-700",
  blocked: "bg-red-100 text-red-700",
  none: "bg-slate-100 text-slate-600",
};

function ScoreCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-xs text-slate-500">
      <span className="font-medium text-slate-700">{value}</span> {label}
    </div>
  );
}

export default function PreferredSuppliersAdminPage() {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator";

  const [rows, setRows] = useState<PreferredSupplierStatus[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Override modal state
  const [overrideTarget, setOverrideTarget] = useState<PreferredSupplierStatus | null>(null);
  const [overrideStatus, setOverrideStatus] = useState("preferred");
  const [overrideReason, setOverrideReason] = useState("");

  // Qualification quick-set state
  const [qualTarget, setQualTarget] = useState<PreferredSupplierStatus | null>(null);
  const [qualScore, setQualScore] = useState("80");

  const supplierNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const supplier of suppliers) map[supplier.id] = supplier.name;
    return map;
  }, [suppliers]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [statuses, supplierList] = await Promise.all([
        listPreferredStatuses(statusFilter ? { status: statusFilter } : undefined),
        listSuppliers(),
      ]);
      setRows(statuses.items);
      setSuppliers(supplierList.items ?? []);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  async function handleRecomputeAll() {
    if (!isAdmin) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await recomputeAllPreferredStatuses();
      setNotice(`Recomputed ${result.total} supplier(s).`);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRecomputeOne(supplierId: string) {
    setBusy(true);
    setError(null);
    try {
      await recomputePreferredStatus(supplierId);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleOverrideSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!overrideTarget || !isAdmin) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await overridePreferredStatus(overrideTarget.supplier_id, {
        status: overrideStatus,
        reason: overrideReason,
      });
      setNotice(
        result.applied
          ? "Override applied (no review workflow configured)."
          : "Override submitted for review: Category Manager → Procurement Head → Risk Team → Compliance. It applies when all reviewers approve."
      );
      setOverrideTarget(null);
      setOverrideReason("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleQualificationSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!qualTarget) return;
    setBusy(true);
    setError(null);
    try {
      await upsertSupplierQualification(qualTarget.supplier_id, { score: Number(qualScore) });
      // Qualification changed -- refresh this supplier's composite too.
      await recomputePreferredStatus(qualTarget.supplier_id);
      setQualTarget(null);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Preferred Supplier Management</h2>
          <p className="mt-1 text-sm text-slate-500">
            Composite score = 30% qualification + 30% performance + 20% risk favorability + 20% spend
            tier. Strategic requires a score of 90+ and an active contract.
          </p>
        </div>
        {isAdmin && (
          <button className="btn-primary" onClick={() => void handleRecomputeAll()} disabled={busy}>
            {busy ? "Working..." : "Recompute all"}
          </button>
        )}
      </div>

      {!isAdmin && (
        <div className="card text-sm text-slate-500">
          You can view preferred supplier statuses, but only administrators can recompute or
          override them.
        </div>
      )}
      {error && <div className="card border border-red-200 bg-red-50 text-sm text-red-700">{error}</div>}
      {notice && <div className="card border border-green-200 bg-green-50 text-sm text-green-700">{notice}</div>}

      <div className="card space-y-4">
        <div className="flex items-center gap-3">
          <label className="label mb-0" htmlFor="status-filter">
            Status
          </label>
          <select
            id="status-filter"
            className="input-field max-w-44"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-slate-500">
            No preferred statuses computed yet. Use &quot;Recompute all&quot; to score every active
            supplier from live qualification, performance, risk, and spend data.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4">Supplier</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Composite</th>
                  <th className="py-2 pr-4">Breakdown</th>
                  <th className="py-2 pr-4">Contract</th>
                  <th className="py-2 pr-4">Reason</th>
                  {isAdmin && <th className="py-2">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b align-top last:border-0">
                    <td className="py-3 pr-4 font-medium text-slate-800">
                      {supplierNames[row.supplier_id] ?? row.supplier_id.slice(0, 8)}
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`badge capitalize ${statusColors[row.preferred_status] ?? statusColors.none}`}>
                        {row.preferred_status}
                      </span>
                      {row.override_flag && (
                        <div className="mt-1 text-xs text-amber-600" title={row.override_reason ?? undefined}>
                          manual override
                        </div>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-base font-semibold text-slate-900">
                      {row.composite_score ?? "—"}
                    </td>
                    <td className="py-3 pr-4 space-y-0.5">
                      <ScoreCell label="qualification" value={row.qualification_score?.toString() ?? "—"} />
                      <ScoreCell label="performance" value={row.performance_score ?? "—"} />
                      <ScoreCell label="risk" value={row.risk_score?.toString() ?? "—"} />
                      <ScoreCell label="spend tier" value={row.spend_tier?.toString() ?? "—"} />
                    </td>
                    <td className="py-3 pr-4 text-xs text-slate-600">
                      {row.has_active_contract ? "Active" : "None"}
                      {(row.preferred_status === "preferred" || row.preferred_status === "strategic") &&
                        !row.has_active_contract && (
                          <div className="mt-1 text-amber-600">No active contract</div>
                        )}
                    </td>
                    <td className="max-w-64 py-3 pr-4 text-xs text-slate-500">
                      {row.classification_reason ?? "—"}
                    </td>
                    {isAdmin && (
                      <td className="space-y-1 py-3 text-xs">
                        <button
                          className="btn-secondary block w-full"
                          disabled={busy}
                          onClick={() => void handleRecomputeOne(row.supplier_id)}
                        >
                          Recompute
                        </button>
                        <button
                          className="btn-secondary block w-full"
                          disabled={busy}
                          onClick={() => {
                            setOverrideTarget(row);
                            setOverrideStatus(row.preferred_status === "blocked" ? "approved" : "preferred");
                          }}
                        >
                          Override
                        </button>
                        <button
                          className="btn-secondary block w-full"
                          disabled={busy}
                          onClick={() => {
                            setQualTarget(row);
                            setQualScore(row.qualification_score?.toString() ?? "80");
                          }}
                        >
                          Set qualification
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

      {overrideTarget && (
        <div className="card space-y-4 border border-amber-200">
          <h3 className="text-lg font-medium">
            Override status for {supplierNames[overrideTarget.supplier_id] ?? "supplier"}
          </h3>
          <form onSubmit={handleOverrideSubmit} className="space-y-4">
            <div>
              <label className="label" htmlFor="override-status">
                New status
              </label>
              <select
                id="override-status"
                className="input-field max-w-44"
                value={overrideStatus}
                onChange={(e) => setOverrideStatus(e.target.value)}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="override-reason">
                Reason (required, audited)
              </label>
              <textarea
                id="override-reason"
                required
                minLength={5}
                className="input-field min-h-20"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Why is the engine-computed status being overridden?"
              />
            </div>
            <div className="flex gap-3">
              <button type="submit" className="btn-primary" disabled={busy || overrideReason.trim().length < 5}>
                Submit override
              </button>
              <button type="button" className="btn-secondary" onClick={() => setOverrideTarget(null)}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {qualTarget && (
        <div className="card space-y-4 border border-blue-200">
          <h3 className="text-lg font-medium">
            Set qualification for {supplierNames[qualTarget.supplier_id] ?? "supplier"}
          </h3>
          <p className="text-xs text-slate-500">
            Manual placeholder entry -- stands in for the future template-driven qualification
            module. Grade is derived server-side (A: 90+, B: 80+, C: 70+, D: 60+, F below).
          </p>
          <form onSubmit={handleQualificationSubmit} className="flex items-end gap-3">
            <div>
              <label className="label" htmlFor="qual-score">
                Score (0-100)
              </label>
              <input
                id="qual-score"
                type="number"
                min={0}
                max={100}
                required
                className="input-field max-w-28"
                value={qualScore}
                onChange={(e) => setQualScore(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-primary" disabled={busy}>
              Save &amp; recompute
            </button>
            <button type="button" className="btn-secondary" onClick={() => setQualTarget(null)}>
              Cancel
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
