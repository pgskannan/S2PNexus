"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  extractErrorMessage,
  getSupplier,
  getSupplierDuplicates,
  getSupplierHierarchy,
  getSupplierSpendRollup,
  listSuppliers,
  mergeSuppliers,
  transitionSupplierLifecycle,
  updateSupplierHierarchy,
} from "@/lib/api";
import type {
  Supplier,
  SupplierDuplicateCandidate,
  SupplierHierarchyResponse,
  SupplierRelationshipType,
} from "@/lib/types";

const lifecycleActions: Record<
  string,
  { action: string; label: string; style: "btn-primary" | "btn-secondary"; needsReason?: boolean }[]
> = {
  active: [
    { action: "begin_monitoring", label: "Begin monitoring", style: "btn-secondary" },
    { action: "flag_requalification", label: "Flag for requalification", style: "btn-secondary" },
    { action: "start_offboarding", label: "Start offboarding", style: "btn-secondary", needsReason: true },
  ],
  under_monitoring: [
    { action: "flag_requalification", label: "Flag for requalification", style: "btn-secondary" },
    { action: "start_offboarding", label: "Start offboarding", style: "btn-secondary", needsReason: true },
  ],
  requalification_due: [
    { action: "start_requalification", label: "Start requalification", style: "btn-primary" },
    { action: "start_offboarding", label: "Start offboarding", style: "btn-secondary", needsReason: true },
  ],
  requalification_in_progress: [
    { action: "complete_requalification", label: "Mark requalified", style: "btn-primary" },
    { action: "start_offboarding", label: "Start offboarding", style: "btn-secondary", needsReason: true },
  ],
  offboarding: [
    { action: "complete_offboarding", label: "Complete offboarding", style: "btn-primary" },
  ],
  offboarded: [{ action: "reactivate", label: "Reactivate", style: "btn-primary" }],
  merged: [],
};

const lifecycleColors: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  under_monitoring: "bg-amber-100 text-amber-700",
  requalification_due: "bg-amber-100 text-amber-700",
  requalification_in_progress: "bg-blue-100 text-blue-700",
  offboarding: "bg-slate-200 text-slate-700",
  offboarded: "bg-slate-100 text-slate-500",
  merged: "bg-purple-100 text-purple-700",
};

const relationshipTypes: SupplierRelationshipType[] = [
  "subsidiary",
  "affiliate",
  "branch",
  "plant",
];

export default function SupplierDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [hierarchy, setHierarchy] = useState<SupplierHierarchyResponse | null>(null);
  const [spendRollup, setSpendRollup] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<SupplierDuplicateCandidate[]>([]);
  const [allSuppliers, setAllSuppliers] = useState<Supplier[]>([]);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [offboardReason, setOffboardReason] = useState("");
  const [showReasonFor, setShowReasonFor] = useState<string | null>(null);

  const [parentSelection, setParentSelection] = useState("");
  const [relationshipSelection, setRelationshipSelection] = useState<SupplierRelationshipType>("subsidiary");

  async function load() {
    try {
      const [supplierData, hierarchyData, rollupData, duplicatesData, suppliersData] = await Promise.all([
        getSupplier(params.id),
        getSupplierHierarchy(params.id),
        getSupplierSpendRollup(params.id),
        getSupplierDuplicates(params.id),
        listSuppliers(),
      ]);
      setSupplier(supplierData);
      setHierarchy(hierarchyData);
      setSpendRollup(rollupData.total_spend);
      setDuplicates(duplicatesData.candidates);
      setAllSuppliers(suppliersData.items.filter((s) => s.id !== params.id));
      setParentSelection(hierarchyData.parent?.id ?? "");
      if (hierarchyData.parent?.relationship_type) {
        setRelationshipSelection(hierarchyData.parent.relationship_type);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleTransition(action: string, needsReason?: boolean) {
    if (needsReason && showReasonFor !== action) {
      setShowReasonFor(action);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await transitionSupplierLifecycle(params.id, {
        action,
        reason: needsReason ? offboardReason : undefined,
      });
      setSupplier(updated);
      setShowReasonFor(null);
      setOffboardReason("");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSetParent() {
    setBusy(true);
    setError(null);
    try {
      await updateSupplierHierarchy(params.id, {
        parent_supplier_id: parentSelection || null,
        relationship_type: parentSelection ? relationshipSelection : undefined,
      });
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleClearParent() {
    setBusy(true);
    setError(null);
    try {
      await updateSupplierHierarchy(params.id, { parent_supplier_id: null });
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleMerge(candidateId: string) {
    if (!confirm("Merge this candidate into the current supplier record? This reassigns its contracts and cannot be undone from here.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await mergeSuppliers({ source_supplier_id: candidateId, target_supplier_id: params.id });
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error && !supplier) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!supplier) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  const actions = lifecycleActions[supplier.lifecycle_status] ?? [];

  return (
    <div className="max-w-3xl space-y-6">
      <button
        onClick={() => router.push("/dashboard/suppliers")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to suppliers
      </button>

      {supplier.lifecycle_status === "merged" && (
        <div className="rounded-lg border border-purple-200 bg-purple-50 p-4 text-sm text-purple-800">
          This supplier record was merged into{" "}
          {supplier.merged_into_supplier_id ? (
            <Link
              href={`/dashboard/suppliers/${supplier.merged_into_supplier_id}`}
              className="font-medium underline"
            >
              another supplier
            </Link>
          ) : (
            "another supplier"
          )}
          . It&apos;s kept for historical reference only.
        </div>
      )}

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold">{supplier.name}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {supplier.description || "No description"}
            </p>
          </div>
          <span className={`badge capitalize ${lifecycleColors[supplier.lifecycle_status] ?? "bg-slate-100 text-slate-700"}`}>
            {supplier.lifecycle_status.replace(/_/g, " ")}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Contact email</dt>
            <dd>{supplier.contact_email || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Payment terms</dt>
            <dd>{supplier.payment_terms || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Website</dt>
            <dd>{supplier.website || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Tax ID</dt>
            <dd>{supplier.tax_id || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Last qualified</dt>
            <dd>
              {supplier.last_qualified_at
                ? new Date(supplier.last_qualified_at).toLocaleDateString()
                : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Next requalification due</dt>
            <dd>
              {supplier.next_requalification_due_at
                ? new Date(supplier.next_requalification_due_at).toLocaleDateString()
                : "—"}
            </dd>
          </div>
        </dl>

        {error && <p className="text-sm text-red-600">{error}</p>}

        {actions.length > 0 && (
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <div className="flex flex-wrap gap-3">
              {actions.map((a) => (
                <button
                  key={a.action}
                  disabled={busy}
                  onClick={() => handleTransition(a.action, a.needsReason)}
                  className={a.style}
                >
                  {a.label}
                </button>
              ))}
            </div>
            {showReasonFor && (
              <div className="flex gap-2">
                <input
                  className="input-field"
                  placeholder="Reason for offboarding..."
                  value={offboardReason}
                  onChange={(e) => setOffboardReason(e.target.value)}
                />
                <button
                  disabled={busy || !offboardReason.trim()}
                  onClick={() => handleTransition(showReasonFor, true)}
                  className="btn-primary"
                >
                  Confirm
                </button>
                <button
                  onClick={() => {
                    setShowReasonFor(null);
                    setOffboardReason("");
                  }}
                  className="btn-secondary"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}
        {actions.length === 0 && supplier.lifecycle_status !== "merged" && (
          <p className="border-t border-slate-100 pt-4 text-sm text-slate-400">
            No further lifecycle transitions available.
          </p>
        )}
      </div>

      {/* Hierarchy */}
      <div className="card space-y-4">
        <h2 className="font-semibold">Corporate hierarchy</h2>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Parent</dt>
            <dd>
              {hierarchy?.parent ? (
                <>
                  <Link
                    href={`/dashboard/suppliers/${hierarchy.parent.id}`}
                    className="text-brand-700 hover:underline"
                  >
                    {hierarchy.parent.name}
                  </Link>{" "}
                  <span className="text-slate-500">({hierarchy.parent.relationship_type})</span>
                </>
              ) : (
                "None"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Spend roll-up (this + descendants)</dt>
            <dd>
              {spendRollup !== null ? `${supplier.currency} ${spendRollup}` : "—"}
            </dd>
          </div>
        </div>

        <div>
          <dt className="text-sm text-slate-500">Children</dt>
          {hierarchy && hierarchy.children.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {hierarchy.children.map((child) => (
                <li key={child.id}>
                  <Link
                    href={`/dashboard/suppliers/${child.id}`}
                    className="text-brand-700 hover:underline"
                  >
                    {child.name}
                  </Link>{" "}
                  <span className="text-slate-500">({child.relationship_type})</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-sm text-slate-400">No child suppliers.</p>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Parent supplier</label>
            <select
              className="input-field"
              value={parentSelection}
              onChange={(e) => setParentSelection(e.target.value)}
            >
              <option value="">— None —</option>
              {allSuppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">Relationship</label>
            <select
              className="input-field"
              value={relationshipSelection}
              onChange={(e) => setRelationshipSelection(e.target.value as SupplierRelationshipType)}
              disabled={!parentSelection}
            >
              {relationshipTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <button disabled={busy} onClick={handleSetParent} className="btn-primary">
            Save
          </button>
          {hierarchy?.parent && (
            <button disabled={busy} onClick={handleClearParent} className="btn-secondary">
              Detach from parent
            </button>
          )}
        </div>
      </div>

      {/* Duplicates */}
      <div className="card space-y-4">
        <h2 className="font-semibold">Potential duplicates</h2>
        {duplicates.length === 0 && (
          <p className="text-sm text-slate-400">No likely duplicates found.</p>
        )}
        {duplicates.length > 0 && (
          <ul className="space-y-2">
            {duplicates.map((candidate) => (
              <li
                key={candidate.supplier_id}
                className="flex items-center justify-between rounded-lg border border-slate-200 p-3 text-sm"
              >
                <div>
                  <Link
                    href={`/dashboard/suppliers/${candidate.supplier_id}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {candidate.name}
                  </Link>
                  <p className="text-slate-500">
                    {Math.round(candidate.match_score * 100)}% match — {candidate.match_reasons.join(", ")}
                  </p>
                </div>
                <button
                  disabled={busy}
                  onClick={() => handleMerge(candidate.supplier_id)}
                  className="btn-secondary"
                >
                  Merge into this record
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
