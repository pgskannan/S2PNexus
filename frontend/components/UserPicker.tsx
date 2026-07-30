"use client";

import { useEffect, useRef, useState } from "react";
import { listUsers } from "@/lib/api";

export default function UserPicker({
  value,
  onChange,
  multiple = false,
  placeholder = "Search users...",
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  multiple?: boolean;
  placeholder?: string;
}) {
  const [results, setResults] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
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

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await listUsers({ search: query, limit: 25 });
        setResults(res.items);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  }, [query]);

  function pick(user: any) {
    if (multiple) {
      if (!value.includes(user.id)) onChange([...value, user.id]);
    } else {
      onChange([user.id]);
      setOpen(false);
    }
  }

  function remove(id: string) {
    onChange(value.filter((v) => v !== id));
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="flex flex-wrap gap-2">
        {value.map((id) => (
          <span key={id} className="rounded-full bg-slate-100 px-2 py-1 text-xs">
            {id} <button onClick={() => remove(id)} className="ml-2 text-red-600">x</button>
          </span>
        ))}
        <input
          className="input-field"
          placeholder={placeholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
        />
      </div>
      {open && (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {loading && <div className="px-3 py-2 text-sm text-slate-400">Searching...</div>}
          {!loading && results.length === 0 && <div className="px-3 py-2 text-sm text-slate-400">No matches</div>}
          {!loading && results.map((u) => (
            <button key={u.id} type="button" onClick={() => pick(u)} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50">
              <div className="font-medium">{u.full_name}</div>
              <div className="text-xs text-slate-500">{u.email}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
