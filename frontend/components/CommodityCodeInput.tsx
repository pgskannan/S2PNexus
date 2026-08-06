"use client";

import { useEffect, useRef, useState } from "react";
import { searchCommodityCodes } from "@/lib/api";
import type { CommodityCodeResult } from "@/lib/types";

// Free-text input backed by an autocomplete dropdown against
// GET /commodity-codes?search=... . The value stored/submitted is always the
// raw code string (matches ProcurementRequisitionLineItemCreate.commodity),
// not a foreign key -- picking a suggestion just fills the field with its
// `code`, same as if the user had typed it by hand.
export default function CommodityCodeInput({
  id,
  value,
  onChange,
  placeholder = "Search commodity code or title...",
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [results, setResults] = useState<CommodityCodeResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleInputChange(next: string) {
    onChange(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!next.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const items = await searchCommodityCodes(next);
        setResults(items);
        setOpen(items.length > 0);
      } catch {
        // Autocomplete failures shouldn't block manual entry -- the field
        // still works as a plain text input if the search call fails.
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  }

  // "Browse" lists whatever commodity codes exist (up to the backend's
  // default limit) with no search term -- useful when the user doesn't know
  // a code/title to type yet, or just wants to see what's loaded.
  async function browseAll() {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setLoading(true);
    setOpen(true);
    try {
      const items = await searchCommodityCodes();
      setResults(items);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function pick(item: CommodityCodeResult) {
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
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
        />
        <button
          type="button"
          onClick={browseAll}
          className="btn-secondary shrink-0 px-2 text-xs"
          title="Browse all commodity codes"
        >
          Browse
        </button>
      </div>
      {open && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {loading && (
            <div className="px-3 py-2 text-sm text-slate-400">Searching...</div>
          )}
          {!loading && results.length === 0 && (
            <div className="px-3 py-2 text-sm text-slate-400">No matches</div>
          )}
          {!loading &&
            results.map((item) => (
              <button
                type="button"
                key={item.code}
                onClick={() => pick(item)}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="font-mono text-xs text-slate-500">
                  {item.code}
                </span>{" "}
                <span>
                  {item.commodity_title ||
                    item.class_title ||
                    item.family_title ||
                    item.segment_title ||
                    "—"}
                </span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
