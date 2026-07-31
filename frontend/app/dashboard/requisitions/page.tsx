"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { listRequisitions, listSuppliers, listUserDirectory, deleteRequisition, transitionRequisition, extractErrorMessage, type UserDirectoryEntry } from "@/lib/api";
import CategoryInput from "@/components/CategoryInput";
import { StatusBadge } from "@/components/StatusBadge";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import ProcurementTabs from "@/components/ProcurementTabs";
import type { Requisition, Supplier } from "@/lib/types";

type StatusFilter = "" | "draft" | "submitted" | "pending_approval" | "approved" | "rejected" | "returned" | "po_created" | "closed";
type SortField = "requisition_number" | "title" | "priority" | "estimated_value" | "created_at";

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: "", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "submitted", label: "Submitted" },
  { key: "pending_approval", label: "Pending approval" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "returned", label: "Needs rework" },
  { key: "po_created", label: "PO created" },
  { key: "closed", label: "Closed" },
];

const HIGH_VALUE_THRESHOLD = 10000;

interface RequisitionQueryParams {
  search?: string;
  status?: string;
  category?: string;
  supplier_id?: string;
  created_after?: string;
  created_before?: string;
  priority?: string;
  estimated_value_min?: number;
  estimated_value_max?: number;
  requested_by?: string;
  limit?: number;
  skip?: number;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) return <>{text}</>;
  const pattern = new RegExp(`(${escapeRegExp(normalizedQuery)})`, "ig");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        part.toLowerCase() === normalizedQuery.toLowerCase() ? (
          <mark key={`${part}-${index}`} className="rounded bg-amber-100 px-0.5 text-slate-900">
            {part}
          </mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        )
      )}
    </>
  );
}

function SortHeader({
  label,
  field,
  sortField,
  sortDirection,
  onSort,
}: {
  label: string;
  field: SortField;
  sortField: SortField;
  sortDirection: "asc" | "desc";
  onSort: (field: SortField) => void;
}) {
  const active = sortField === field;
  return (
    <th className="px-4 py-3">
      <button
        type="button"
        onClick={() => onSort(field)}
        className={`inline-flex items-center gap-1 hover:text-slate-700 ${active ? "text-slate-700" : ""}`}
      >
        {label}
        {active && <span>{sortDirection === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}

export default function RequisitionsPage() {
  const [items, setItems] = useState<Requisition[]>([]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [category, setCategory] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [priority, setPriority] = useState("");
  const [valueMin, setValueMin] = useState("");
  const [valueMax, setValueMax] = useState("");
  const [requestedBy, setRequestedBy] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [users, setUsers] = useState<UserDirectoryEntry[]>([]);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [highValueCount, setHighValueCount] = useState(0);
  const [sortField, setSortField] = useState<SortField>("created_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const activeFilterCount = [category, supplierId, priority, requestedBy, valueMin, valueMax, createdAfter, createdBefore].filter(
    (v) => v
  ).length;

  const usersById = useMemo(() => {
    const map: Record<string, string> = {};
    users.forEach((u) => {
      map[u.id] = u.full_name || u.email;
    });
    return map;
  }, [users]);

  function baseParams(overrides?: Partial<RequisitionQueryParams>): RequisitionQueryParams {
    return {
      search: search || undefined,
      category: category || undefined,
      supplier_id: supplierId || undefined,
      created_after: createdAfter || undefined,
      created_before: createdBefore || undefined,
      priority: priority || undefined,
      estimated_value_min: valueMin ? Number(valueMin) : undefined,
      estimated_value_max: valueMax ? Number(valueMax) : undefined,
      requested_by: requestedBy || undefined,
      ...overrides,
    };
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listRequisitions(baseParams({ status: status || undefined }));
      setItems(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function loadCounts() {
    try {
      const statuses: StatusFilter[] = ["draft", "submitted", "pending_approval", "approved", "rejected", "returned", "po_created", "closed"];
      const [all, ...perStatus] = await Promise.all([
        listRequisitions(baseParams({ status: undefined, limit: 1 })),
        ...statuses.map((s) => listRequisitions(baseParams({ status: s, limit: 1 }))),
      ]);
      const counts: Record<string, number> = { "": all.total };
      statuses.forEach((s, i) => {
        counts[s] = perStatus[i].total;
      });
      setStatusCounts(counts);
      const highValue = await listRequisitions(baseParams({ status: undefined, estimated_value_min: HIGH_VALUE_THRESHOLD, limit: 1 }));
      setHighValueCount(highValue.total);
    } catch {
      // Best-effort only -- the pills/strip degrade to showing 0 rather than
      // blocking the main list from rendering.
    }
  }

  useEffect(() => {
    load();
    loadCounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, status, category, supplierId, createdAfter, createdBefore, priority, valueMin, valueMax, requestedBy]);

  useEffect(() => {
    listSuppliers()
      .then((r) => setSuppliers(r.items))
      .catch(() => setSuppliers([]));
    listUserDirectory({ limit: 500 })
      .then((r) => setUsers(r.items))
      .catch(() => setUsers([]));
  }, []);

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("asc");
    }
  }

  const sortedItems = useMemo(() => {
    const data = [...items];
    data.sort((a, b) => {
      let aVal: string | number = "";
      let bVal: string | number = "";
      if (sortField === "estimated_value") {
        aVal = a.estimated_value ? Number(a.estimated_value) : 0;
        bVal = b.estimated_value ? Number(b.estimated_value) : 0;
      } else {
        aVal = (a[sortField] as string) || "";
        bVal = (b[sortField] as string) || "";
      }
      if (aVal === bVal) return 0;
      const cmp = aVal > bVal ? 1 : -1;
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return data;
  }, [items, sortField, sortDirection]);

  async function handleDelete(id: string) {
    if (!confirm("Delete this draft requisition? This cannot be undone.")) {
      return;
    }
    try {
      await deleteRequisition(id);
      setItems((prev) => prev.filter((r) => r.id !== id));
      loadCounts();
    } catch (err) {
      alert("Delete failed: " + extractErrorMessage(err));
    }
  }

  async function handleWithdraw(id: string) {
    if (!confirm("Withdraw this submitted requisition? It will no longer be available for approval.")) {
      return;
    }
    try {
      await transitionRequisition(id, "cancelled", "cancelled");
      await load();
      await loadCounts();
    } catch (err) {
      alert("Withdraw failed: " + extractErrorMessage(err));
    }
  }

  async function handleExport() {
    try {
      const res = await listRequisitions(baseParams({ status: status || undefined, limit: 1000 }));
      const rows = res.items;
      const cols = ["requisition_number", "title", "status", "priority", "estimated_value", "currency", "created_at"];
      const csv = [cols.join(",")]
        .concat(
          rows.map((r) =>
            cols
              .map((c) => {
                const v = (r as unknown as Record<string, unknown>)[c];
                if (v === undefined || v === null) return "";
                return String(v).replace(/"/g, '""');
              })
              .map((v) => `"${v}"`)
              .join(",")
          )
        )
        .join("\n");
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "requisitions_export.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("Export failed: " + extractErrorMessage(err));
    }
  }

  // "submitted" is now a brief transitional state -- the backend advances a
  // requisition to "pending_approval" as soon as its workflow instance is
  // created (same request as Submit), so counting "submitted" alone almost
  // always reads 0 even when approvals are genuinely waiting.
  const pendingCount = (statusCounts["submitted"] ?? 0) + (statusCounts["pending_approval"] ?? 0);
  const draftCount = statusCounts["draft"] ?? 0;
  const recommendation =
    pendingCount > 0
      ? `${pendingCount} requisition(s) are pending approval. Prioritize high-value or older requests to avoid cycle delays.`
      : draftCount > 0
      ? `${draftCount} draft requisition(s) are ready for completion. Submit ready drafts to keep throughput steady.`
      : "Approval queue is clear. Focus on new demand intake.";

  return (
    <div className="space-y-6">
      <ProcurementTabs />
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Requisitions</h1>
        <Link href="/dashboard/requisitions/new" className="btn-primary">
          + New Requisition
        </Link>
      </div>

      <ActionRecommendationStrip
        title="Requisition actions"
        description="Jump into pending approvals, monitor high-value spend, or raise a new requisition."
        recommendation={recommendation}
        actions={[
          {
            label: "Needs approval",
            count: pendingCount,
            tone: "critical",
            onClick: () => setStatus("submitted"),
          },
          {
            label: `High value (>$${HIGH_VALUE_THRESHOLD.toLocaleString()})`,
            count: highValueCount,
            tone: "warning",
            onClick: () => {
              setStatus("");
              setValueMin(String(HIGH_VALUE_THRESHOLD));
            },
          },
        ]}
      />

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => {
          const active = status === tab.key;
          return (
            <button
              key={tab.key || "all"}
              type="button"
              onClick={() => setStatus(tab.key)}
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                active ? "bg-slate-900 text-white" : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              {tab.label}
              <span className={`rounded-full px-1.5 py-0 text-[11px] ${active ? "bg-slate-700 text-white" : "bg-slate-100 text-slate-600"}`}>
                {statusCounts[tab.key] ?? 0}
              </span>
            </button>
          );
        })}
      </div>

      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs text-slate-500">Search</label>
            <input
              className="input-field"
              placeholder="Title, number, description..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-2"
            onClick={() => setFiltersOpen((v) => !v)}
          >
            Filters
            {activeFilterCount > 0 && (
              <span className="rounded-full bg-slate-900 px-1.5 text-xs text-white">{activeFilterCount}</span>
            )}
            <span className="text-xs">{filtersOpen ? "▲" : "▼"}</span>
          </button>
          <button type="button" className="btn-secondary" onClick={handleExport}>
            Export CSV
          </button>
        </div>

        {filtersOpen && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              load();
              loadCounts();
            }}
            className="flex flex-wrap gap-2 items-end border-t border-slate-100 pt-3"
          >
            <div style={{ minWidth: 200 }}>
              <label className="text-xs text-slate-500">Category</label>
              <CategoryInput value={category} onChange={setCategory} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Supplier</label>
              <select className="input-field" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
                <option value="">Any supplier</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Priority</label>
              <select className="input-field" value={priority} onChange={(e) => setPriority(e.target.value)}>
                <option value="">Any priority</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Requested by</label>
              <select className="input-field" value={requestedBy} onChange={(e) => setRequestedBy(e.target.value)}>
                <option value="">Anyone</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name || u.email}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500">Value min</label>
              <input type="number" min="0" className="input-field w-28" value={valueMin} onChange={(e) => setValueMin(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Value max</label>
              <input type="number" min="0" className="input-field w-28" value={valueMax} onChange={(e) => setValueMax(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Created after</label>
              <input type="date" className="input-field" value={createdAfter} onChange={(e) => setCreatedAfter(e.target.value)} />
            </div>
            <div>
              <label className="text-xs text-slate-500">Created before</label>
              <input type="date" className="input-field" value={createdBefore} onChange={(e) => setCreatedBefore(e.target.value)} />
            </div>
            <button type="submit" className="btn-secondary">
              Apply
            </button>
            {activeFilterCount > 0 && (
              <button
                type="button"
                className="text-xs text-red-600 hover:underline"
                onClick={() => {
                  setCategory("");
                  setSupplierId("");
                  setPriority("");
                  setRequestedBy("");
                  setValueMin("");
                  setValueMax("");
                  setCreatedAfter("");
                  setCreatedBefore("");
                }}
              >
                Clear filters
              </button>
            )}
          </form>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <SortHeader label="Number" field="requisition_number" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <SortHeader label="Title" field="title" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <th className="px-4 py-3">Requester</th>
              <th className="px-4 py-3">Status</th>
              <SortHeader label="Priority" field="priority" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <SortHeader label="Est. value" field="estimated_value" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <SortHeader label="Created" field="created_at" sortField={sortField} sortDirection={sortDirection} onSort={handleSort} />
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={8}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && sortedItems.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={8}>
                  No requisitions match these filters.
                </td>
              </tr>
            )}
            {sortedItems.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono text-xs text-slate-500">
                  <HighlightedText text={item.requisition_number || "—"} query={search} />
                </td>
                <td className="px-4 py-3">
                  <Link href={`/dashboard/requisitions/${item.id}`} className="font-medium text-brand-700 hover:underline">
                    <HighlightedText text={item.title} query={search} />
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-500">{usersById[item.requested_by] || "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={item.lifecycle_status} />
                </td>
                <td className="px-4 py-3 capitalize">{item.priority}</td>
                <td className="px-4 py-3">
                  {item.estimated_value ? (
                    Number(item.estimated_value) > HIGH_VALUE_THRESHOLD ? (
                      <span className="font-semibold text-orange-800 bg-orange-50 border border-orange-200 px-2 py-1 rounded">
                        {item.currency} {item.estimated_value}
                      </span>
                    ) : (
                      `${item.currency} ${item.estimated_value}`
                    )
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-4 py-3 text-slate-500">{new Date(item.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  {item.lifecycle_status === "draft" && (
                    <button
                      onClick={() => handleDelete(item.id)}
                      className="text-xs text-red-600 hover:underline"
                      title="Delete draft"
                    >
                      Delete
                    </button>
                  )}
                  {item.lifecycle_status === "submitted" && (
                    <button
                      onClick={() => handleWithdraw(item.id)}
                      className="text-xs text-red-600 hover:underline"
                      title="Withdraw submitted requisition"
                    >
                      Withdraw
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
