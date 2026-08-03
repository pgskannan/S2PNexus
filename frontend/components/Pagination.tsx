"use client";

// Shared pagination control for document list tables (Requisitions, Purchase
// Orders, Receipts, Invoices). Deliberately client-side/display-only: the
// caller passes the full (already-filtered/sorted) items array and this
// component slices it, rather than each page having to be rewired for
// server-side skip/limit. Simpler and lower-risk than touching every list
// endpoint right before the XPRIZE demo -- can be swapped for real
// server-side paging later without changing the table markup.

import { useEffect, useMemo, useState } from "react";

export const DEFAULT_PAGE_SIZE = 10;

export function usePagination<T>(items: T[], pageSize: number = DEFAULT_PAGE_SIZE) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));

  // Clamp back to the last valid page if the filtered set shrinks (e.g. a
  // filter narrows results while sitting on page 4 of what's now 2 pages).
  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  return { page, setPage, totalPages, pageItems, pageSize };
}

export default function Pagination({
  page,
  totalPages,
  totalItems,
  pageSize,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}) {
  if (totalItems === 0) return null;

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, totalItems);

  // Compact page-number list: always show first, last, current +/-1, with
  // "…" gaps -- avoids rendering 50 page buttons for large tables.
  const pageNumbers: (number | "ellipsis")[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || Math.abs(p - page) <= 1) {
      pageNumbers.push(p);
    } else if (pageNumbers[pageNumbers.length - 1] !== "ellipsis") {
      pageNumbers.push("ellipsis");
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
      <p className="text-xs text-slate-500">
        Showing {start}–{end} of {totalItems}
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="btn-secondary px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Previous
        </button>
        {pageNumbers.map((p, idx) =>
          p === "ellipsis" ? (
            <span key={`ellipsis-${idx}`} className="px-1 text-xs text-slate-400">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => onPageChange(p)}
              className={`min-w-[28px] rounded-md px-2 py-1 text-xs font-medium ${
                p === page ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          type="button"
          className="btn-secondary px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next
        </button>
      </div>
    </div>
  );
}
