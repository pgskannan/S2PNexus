"use client";

import { useEffect, useRef, useState } from "react";
import { searchCategories } from "@/lib/api";

export default function CategoryInput({
  id,
  value,
  onChange,
  placeholder = "e.g. IT Hardware",
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  const [results, setResults] = useState<Array<{ code: string; name?: string | null; is_active: boolean }>>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
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
        const items = await searchCategories(next);
        setResults(items as any);
        setOpen((items as any).length > 0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  }

  async function browseAll() {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setLoading(true);
    setOpen(true);
    try {
      const items = await searchCategories();
      setResults(items as any);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function pick(item: { code: string }) {
    onChange(item.code);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="flex gap-1">
        <input
          id={id}
          className="input-field"
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
          title="Browse all categories"
        >
          Browse
        </button>
      </div>
      {open && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {loading && <div className="px-3 py-2 text-sm text-slate-400">Searching...</div>}
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
                <span className="font-mono text-xs text-slate-500">{item.code}</span> <span>{item.name || "—"}</span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
