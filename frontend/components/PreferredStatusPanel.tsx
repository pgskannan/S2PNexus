"use client";

/**
 * Preferred Supplier badge + score breakdown for the supplier detail page
 * (Template Framework Phase 5). Self-contained: fetches its own status, and
 * renders nothing scary when none has been computed yet.
 *
 * Includes the spec Section 18 contract hook as a visible WARNING (not an
 * enforcement block -- nothing else in this codebase hard-blocks on contract
 * coverage, and this batch deliberately doesn't introduce the first one):
 * a preferred/strategic supplier without an active contract gets a banner.
 */

import { useEffect, useState } from "react";
import { getPreferredStatus, recomputePreferredStatus, extractErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type { PreferredSupplierStatus } from "@/lib/types";

const statusColors: Record<string, string> = {
  strategic: "bg-purple-100 text-purple-700",
  preferred: "bg-green-100 text-green-700",
  approved: "bg-blue-100 text-blue-700",
  blocked: "bg-red-100 text-red-700",
  none: "bg-slate-100 text-slate-600",
};

export default function PreferredStatusPanel({ supplierId }: { supplierId: string }) {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator";
  const [status, setStatus] = useState<PreferredSupplierStatus | null>(null);
  const [notComputed, setNotComputed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setStatus(await getPreferredStatus(supplierId));
      setNotComputed(false);
    } catch {
      // 404 = never computed; that's a normal state, not an error.
      setNotComputed(true);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supplierId]);

  async function handleRecompute() {
    setBusy(true);
    setError(null);
    try {
      setStatus(await recomputePreferredStatus(supplierId));
      setNotComputed(false);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const missingContract =
    status !== null &&
    (status.preferred_status === "preferred" || status.preferred_status === "strategic") &&
    !status.has_active_contract;

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Preferred supplier status</h2>
        {isAdmin && (
          <button className="btn-secondary text-xs" onClick={() => void handleRecompute()} disabled={busy}>
            {busy ? "Computing..." : notComputed ? "Compute" : "Recompute"}
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {notComputed ? (
        <p className="text-sm text-slate-500">
          Not scored yet.{isAdmin ? " Use Compute to classify this supplier from live qualification, performance, risk, and spend data." : ""}
        </p>
      ) : status ? (
        <>
          <div className="flex items-center gap-3">
            <span className={`badge capitalize ${statusColors[status.preferred_status] ?? statusColors.none}`}>
              {status.preferred_status}
            </span>
            {status.composite_score && (
              <span className="text-lg font-semibold text-slate-900">{status.composite_score}</span>
            )}
            {status.override_flag && (
              <span className="text-xs text-amber-600" title={status.override_reason ?? undefined}>
                manual override
              </span>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Qualification</dt>
              <dd className="font-medium">{status.qualification_score ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Performance</dt>
              <dd className="font-medium">{status.performance_score ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Risk score</dt>
              <dd className="font-medium">{status.risk_score ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Spend tier</dt>
              <dd className="font-medium">{status.spend_tier ?? "—"}</dd>
            </div>
          </dl>

          {status.classification_reason && (
            <p className="text-xs text-slate-500">{status.classification_reason}</p>
          )}

          {missingContract && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              This supplier is {status.preferred_status} but has <strong>no active contract</strong>.
              Preferred and strategic suppliers should be under contract — consider initiating one.
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-500">Loading...</p>
      )}
    </div>
  );
}
