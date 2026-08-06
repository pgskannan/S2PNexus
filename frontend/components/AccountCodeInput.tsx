"use client";

import { useEffect, useRef, useState } from "react";
import { listGlAccounts, type GlAccount } from "@/lib/api";

// GL/account code picker for requisition & PO line items. 2026-08-05: this
// field previously had no UI input anywhere -- it existed on the data model
// and was checked by the PO auto-creation gate (_po_creation_blockers), but
// nobody could actually fill it in, so approved PRs silently landed in
// "Exception" status with no way to fix them going forward. The chart of
// accounts is small admin-uploaded master data with no server-side search
// endpoint (unlike commodity codes / categories), so this fetches the full
// list once and filters client-side instead of debouncing a search call.
export default function AccountCodeInput({
  id,
  value,
  onChange,
  placeholder = "Search GL/account code...",
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [allAccounts, setAllAccounts] = useState<GlAccount[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    listGlAccounts()
      .then((items) => setAllAccounts(items.filter((a) => a.is_active)))
      .catch(() => setAllAccounts([]))
      .finally(() => setLoaded(true));
  }, []);

  const query = value.trim().toLowerCase();
  const filtered = query
    ? allAccounts.filter(
        (a) => a.code.toLowerCase().includes(query) || (a.description || "").toLowerCase().includes(query)
      )
    : allAccounts;

  function pick(item: GlAccount) {
    onChange(item.code);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="flex gap-1">
        <input
          id={id}
          className="input-field min-w-0 flex-1"
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
        />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="btn-secondary shrink-0 px-2 text-xs"
          title="Browse all GL accounts"
        >
          Browse
        </button>
      </div>
      {open && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {!loaded && <div className="px-3 py-2 text-sm text-slate-400">Loading...</div>}
          {loaded && filtered.length === 0 && (
            <div className="px-3 py-2 text-sm text-slate-400">
              {allAccounts.length === 0
                ? "No GL accounts loaded. Ask an admin to upload the chart of accounts."
                : "No matches"}
            </div>
          )}
          {loaded &&
            filtered.slice(0, 50).map((item) => (
              <button
                type="button"
                key={item.code}
                onClick={() => pick(item)}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="font-mono text-xs text-slate-500">{item.code}</span>{" "}
                <span>{item.description || "—"}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
