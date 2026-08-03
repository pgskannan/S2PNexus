"use client";

/**
 * Supplier invitation picker for a sourcing event (Template Framework
 * Phase 5, spec Section 18 sourcing hook).
 *
 * Preferred/strategic suppliers are auto-recommended: sorted to the top with
 * their status badge and composite score. Inviting a NON-preferred supplier
 * asks for a short justification first -- deliberately a UI nudge, not a
 * hard gate (nothing in the backend blocks the invitation, and the
 * justification is a confirmation step, not persisted master data -- the
 * invitation model has no notes column and this batch doesn't add one).
 * Blocked suppliers get the strongest warning but can still be invited by
 * a user who justifies it.
 */

import { useEffect, useMemo, useState } from "react";
import {
  extractErrorMessage,
  inviteSupplierToSourcingEvent,
  listPreferredStatuses,
  listSuppliers,
} from "@/lib/api";
import type { PreferredSupplierStatus, SourcingEvent, Supplier } from "@/lib/types";

const statusRank: Record<string, number> = {
  strategic: 0,
  preferred: 1,
  approved: 2,
  none: 3,
  blocked: 4,
};

const statusColors: Record<string, string> = {
  strategic: "bg-purple-100 text-purple-700",
  preferred: "bg-green-100 text-green-700",
  approved: "bg-blue-100 text-blue-700",
  blocked: "bg-red-100 text-red-700",
  none: "bg-slate-100 text-slate-600",
};

export default function InviteSuppliersCard({
  event,
  onInvited,
}: {
  event: SourcingEvent;
  onInvited: () => void;
}) {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [preferred, setPreferred] = useState<Record<string, PreferredSupplierStatus>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justifyFor, setJustifyFor] = useState<string | null>(null);
  const [justification, setJustification] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const [supplierList, statuses] = await Promise.all([listSuppliers(), listPreferredStatuses()]);
        setSuppliers(supplierList.items ?? []);
        const map: Record<string, PreferredSupplierStatus> = {};
        for (const status of statuses.items) map[status.supplier_id] = status;
        setPreferred(map);
      } catch (err) {
        setError(extractErrorMessage(err));
      }
    })();
  }, []);

  const invitedIds = useMemo(
    () => new Set(event.invitations.map((invitation) => invitation.supplier_id)),
    [event.invitations]
  );

  const candidates = useMemo(() => {
    return suppliers
      .filter((supplier) => !invitedIds.has(supplier.id))
      .map((supplier) => ({
        supplier,
        status: preferred[supplier.id]?.preferred_status ?? "none",
        score: preferred[supplier.id]?.composite_score ?? null,
      }))
      .sort(
        (a, b) =>
          (statusRank[a.status] ?? 3) - (statusRank[b.status] ?? 3) ||
          a.supplier.name.localeCompare(b.supplier.name)
      );
  }, [suppliers, preferred, invitedIds]);

  const isRecommended = (status: string) => status === "preferred" || status === "strategic";

  const supplierNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const supplier of suppliers) map[supplier.id] = supplier.name;
    return map;
  }, [suppliers]);

  async function invite(supplierId: string) {
    setBusy(true);
    setError(null);
    try {
      await inviteSupplierToSourcingEvent(event.id, supplierId);
      setJustifyFor(null);
      setJustification("");
      onInvited();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function handleInviteClick(supplierId: string, status: string) {
    if (isRecommended(status)) {
      void invite(supplierId); // recommended: one click, no friction
    } else {
      setJustifyFor(supplierId); // nudge: explain why a non-preferred supplier
      setJustification("");
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h2 className="font-semibold">Invite suppliers</h2>
      <p className="mt-1 text-xs text-slate-500">
        Preferred and strategic suppliers are recommended and listed first. Inviting others asks
        for a brief justification.
      </p>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {event.invitations.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500">Invited</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {event.invitations.map((invitation) => (
              <li key={invitation.id} className="flex items-center justify-between rounded bg-slate-50 p-2">
                <span className="flex items-center gap-2">
                  {supplierNames[invitation.supplier_id] ?? `${invitation.supplier_id.slice(0, 8)}…`}
                  {preferred[invitation.supplier_id] && (
                    <span
                      className={`badge capitalize ${
                        statusColors[preferred[invitation.supplier_id].preferred_status] ?? statusColors.none
                      }`}
                    >
                      {preferred[invitation.supplier_id].preferred_status}
                    </span>
                  )}
                </span>
                <span className="badge bg-slate-100 capitalize text-slate-600">{invitation.status}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {candidates.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">All suppliers have been invited.</p>
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {candidates.map(({ supplier, status, score }) => (
            <li key={supplier.id} className="rounded bg-slate-50 p-2">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-800">{supplier.name}</span>
                  <span className={`badge capitalize ${statusColors[status] ?? statusColors.none}`}>
                    {status}
                  </span>
                  {score && <span className="text-xs text-slate-500">{score}</span>}
                  {isRecommended(status) && (
                    <span className="text-xs text-green-700">recommended</span>
                  )}
                  {status === "blocked" && (
                    <span className="text-xs text-red-600">blocked — review before inviting</span>
                  )}
                </div>
                <button
                  className="btn-secondary text-xs"
                  disabled={busy}
                  onClick={() => handleInviteClick(supplier.id, status)}
                >
                  Invite
                </button>
              </div>
              {justifyFor === supplier.id && (
                <div className="mt-2 space-y-2 border-t border-slate-200 pt-2">
                  <label className="label" htmlFor={`justify-${supplier.id}`}>
                    Why invite a non-preferred supplier?
                  </label>
                  <textarea
                    id={`justify-${supplier.id}`}
                    className="input-field min-h-16"
                    value={justification}
                    onChange={(e) => setJustification(e.target.value)}
                    placeholder="e.g. Preferred suppliers can't meet the lead time for this category"
                  />
                  <div className="flex gap-2">
                    <button
                      className="btn-primary text-xs"
                      disabled={busy || justification.trim().length < 5}
                      onClick={() => void invite(supplier.id)}
                    >
                      Invite anyway
                    </button>
                    <button className="btn-secondary text-xs" onClick={() => setJustifyFor(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
