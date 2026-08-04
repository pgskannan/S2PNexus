"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { extractErrorMessage, getPurchaseOrder, getInvoiceExceptions, listInvoices } from "@/lib/api";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import DocumentTabs from "@/components/DocumentTabs";
import Pagination, { usePagination } from "@/components/Pagination";
import type { ProcurementInvoice, ProcurementInvoiceException } from "@/lib/types";

const statusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  matched: "bg-green-100 text-green-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

const HIGH_VALUE_THRESHOLD = 10000;

type QuickFilter = "" | "needs_review" | "high_value";

export default function InvoicesPage() {
  const [items, setItems] = useState<ProcurementInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [poFilter, setPoFilter] = useState<string | null>(null);
  const [poFilterNumber, setPoFilterNumber] = useState<string | null>(null);
  const [prId, setPrId] = useState<string | null>(null);

  // Invoice reconciliation / price-mismatch alerts (backlog Section 5):
  // expandable per-invoice review that surfaces existing match exceptions.
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [exceptionMap, setExceptionMap] = useState<Record<string, ProcurementInvoiceException[]>>({});
  const [exceptionsError, setExceptionsError] = useState<string | null>(null);
  const [exceptionsLoading, setExceptionsLoading] = useState<string | null>(null);

  async function toggleReview(invoice: ProcurementInvoice) {
    if (expandedId === invoice.id) {
      setExpandedId(null);
      return;
    }
    if (!exceptionMap[invoice.id]) {
      setExceptionsLoading(invoice.id);
      setExceptionsError(null);
      try {
        const exceptions = await getInvoiceExceptions(invoice.id);
        setExceptionMap((m) => ({ ...m, [invoice.id]: exceptions }));
      } catch (err) {
        setExceptionsError(extractErrorMessage(err));
      } finally {
        setExceptionsLoading(null);
      }
    }
    setExpandedId(invoice.id);
  }

  function exceptionLabel(type: string): string {
    return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  useEffect(() => {
    listInvoices()
      .then((result) => setItems(result.items))
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const po = params.get("po");
    setPoFilter(po);
    setPoFilterNumber(null);
    if (po) {
      getPurchaseOrder(po)
        .then((p) => {
          setPoFilterNumber(p.order_number);
          setPrId(p.requisition_id ?? null);
        })
        .catch(() => setPoFilterNumber(null));
    }
  }, []);

  function invoiceValue(item: ProcurementInvoice): number {
    const raw = item.total_amount ?? item.amount;
    return raw ? Number(raw) : 0;
  }

  // Scope KPI counts to this PO when a ?po= filter is active -- otherwise the
  // strip reports system-wide totals while the page title/banner claim to be
  // about one specific document, which reads as wrong/irrelevant.
  const scopedItems = useMemo(
    () => (poFilter ? items.filter((item) => item.purchase_order_id === poFilter) : items),
    [items, poFilter]
  );

  const needsReviewCount = scopedItems.filter((item) => item.match_status !== "matched").length;
  const highValueCount = scopedItems.filter((item) => invoiceValue(item) > HIGH_VALUE_THRESHOLD).length;

  const recommendation = poFilter
    ? scopedItems.length === 0
      ? "No invoices exist yet for this purchase order."
      : needsReviewCount > 0
      ? `${needsReviewCount} of ${scopedItems.length} invoice(s) on this PO need review.`
      : highValueCount > 0
      ? `${highValueCount} high-value invoice(s) on this PO. Double-check before payment runs.`
      : "All invoices on this PO are matched. Nothing blocking AP right now."
    : needsReviewCount > 0
    ? `${needsReviewCount} invoice(s) need review. Resolve match exceptions to keep AP current.`
    : highValueCount > 0
    ? `${highValueCount} high-value invoice(s) on the books. Double-check these before payment runs.`
    : "All invoices are matched. Nothing blocking AP right now.";

  const displayedItems = useMemo(() => {
    return scopedItems.filter((item) => {
      if (search && !item.invoice_number.toLowerCase().includes(search.toLowerCase())) return false;
      if (statusFilter && item.status !== statusFilter) return false;
      if (quickFilter === "needs_review" && item.match_status === "matched") return false;
      if (quickFilter === "high_value" && invoiceValue(item) <= HIGH_VALUE_THRESHOLD) return false;
      return true;
    });
  }, [scopedItems, search, statusFilter, quickFilter]);

  const { page, setPage, totalPages, pageItems } = usePagination(displayedItems);

  useEffect(() => {
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayedItems]);

  const activeFilterCount = [statusFilter, quickFilter].filter((v) => v).length;

  return (
    <div className="space-y-6">
      <DocumentTabs prId={prId} poId={poFilter} />
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Invoices</h1>
          <p className="mt-1 text-sm text-slate-500">Monitor invoice status and three-way match progress.</p>
        </div>
        <Link
          href={poFilter ? `/dashboard/invoices/new?po=${poFilter}` : "/dashboard/invoices/new"}
          className="btn-primary"
        >
          + New Invoice
        </Link>
      </div>
      {poFilter && (
        <div className="flex items-center justify-between rounded-md border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-700">
          <span>
            Showing invoices for purchase order{" "}
            <span className="font-mono">{poFilterNumber ?? poFilter}</span>
          </span>
          <button type="button" onClick={() => setPoFilter(null)} className="text-xs font-medium underline">
            Clear filter
          </button>
        </div>
      )}

      <ActionRecommendationStrip
        title={poFilter ? `Invoice actions · PO ${poFilterNumber ?? poFilter}` : "Invoice actions"}
        description="Clear match exceptions and keep an eye on high-value invoices before they're paid."
        recommendation={recommendation}
        actions={[
          {
            label: "Needs review",
            count: needsReviewCount,
            tone: "critical",
            onClick: () => setQuickFilter(quickFilter === "needs_review" ? "" : "needs_review"),
          },
          {
            label: `High value (>$${HIGH_VALUE_THRESHOLD.toLocaleString()})`,
            count: highValueCount,
            tone: "warning",
            onClick: () => setQuickFilter(quickFilter === "high_value" ? "" : "high_value"),
          },
        ]}
      />

      <div className="card space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs text-slate-500">Search</label>
            <input
              className="input-field"
              placeholder="Invoice number..."
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
        </div>

        {filtersOpen && (
          <div className="flex flex-wrap gap-2 items-end border-t border-slate-100 pt-3">
            <div>
              <label className="text-xs text-slate-500">Status</label>
              <select className="input-field" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="matched">Matched</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            {activeFilterCount > 0 && (
              <button
                type="button"
                className="text-xs text-red-600 hover:underline pb-2"
                onClick={() => {
                  setStatusFilter("");
                  setQuickFilter("");
                }}
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Invoice #</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Match</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={5}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && displayedItems.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={5}>
                  No invoices match these filters.
                </td>
              </tr>
            )}
            {pageItems.map((item) => {
              const isException = item.match_status !== "matched";
              const exceptions = exceptionMap[item.id] ?? [];
              const expanded = expandedId === item.id;
              return (
                <Fragment key={item.id}>
                  <tr className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-brand-700">{item.invoice_number}</td>
                    <td className="px-4 py-3">
                      <span className={`badge ${statusColors[item.status] ?? "bg-slate-100 text-slate-700"}`}>
                        {item.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="capitalize">{item.match_status.replace(/_/g, " ")}</span>
                        {isException && (
                          <button
                            type="button"
                            onClick={() => toggleReview(item)}
                            className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700 hover:bg-amber-200"
                          >
                            {exceptionsLoading === item.id
                              ? "Loading…"
                              : expanded
                              ? "Hide"
                              : `Review (${exceptions.length > 0 ? exceptions.length : "…"})`}
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {item.currency} {item.total_amount ?? item.amount}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{new Date(item.created_at).toLocaleDateString()}</td>
                  </tr>
                  {expanded && isException && (
                    <tr className="bg-amber-50/40">
                      <td colSpan={5} className="px-4 py-3">
                        {exceptionsLoading === item.id ? (
                          <p className="text-sm text-slate-500">Loading exceptions…</p>
                        ) : exceptions.length === 0 ? (
                          <p className="text-sm text-slate-500">
                            No match-exception rows on record — this invoice still needs review before it can be
                            paid. <Link href={`/dashboard/invoices/new?invoice=${item.id}`} className="text-brand-600 hover:underline">Edit invoice</Link>
                          </p>
                        ) : (
                          <ul className="space-y-2">
                            {exceptions.map((ex) => (
                              <li key={ex.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded bg-white px-3 py-2 text-sm">
                                <span className="font-semibold text-red-700">{exceptionLabel(ex.exception_type)}</span>
                                {ex.expected_value != null && (
                                  <span className="text-slate-600">
                                    Expected <span className="font-mono">{ex.expected_value}</span>
                                  </span>
                                )}
                                {ex.actual_value != null && (
                                  <span className="text-slate-600">
                                    Actual <span className="font-mono">{ex.actual_value}</span>
                                  </span>
                                )}
                                {ex.variance_amount != null && (
                                  <span className="font-semibold text-amber-700">
                                    Δ {ex.variance_amount}
                                    {ex.variance_percent != null ? ` (${ex.variance_percent}%)` : ""}
                                  </span>
                                )}
                                <span className="text-xs uppercase tracking-wide text-slate-400">
                                  {ex.resolution_status.replace(/_/g, " ")}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                        {exceptionsError && <p className="mt-2 text-sm text-red-600">{exceptionsError}</p>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        <Pagination
          page={page}
          totalPages={totalPages}
          totalItems={displayedItems.length}
          pageSize={10}
          onPageChange={setPage}
        />
      </div>
    </div>
  );
}
