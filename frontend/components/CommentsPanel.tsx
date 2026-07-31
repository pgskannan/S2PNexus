"use client";

import { useState } from "react";
import type { ProcurementComment } from "@/lib/types";

interface CommentsPanelProps {
  items: ProcurementComment[];
  loading: boolean;
  error: string | null;
  authorNames?: Record<string, string>;
  onAdd: (text: string) => Promise<void>;
}

// Shared comment thread used by both the PR and PO detail pages so behavior is
// identical on every document. The parent owns fetching/adding (which differs
// by entity); this component only renders the thread and the add box.
export default function CommentsPanel({
  items,
  loading,
  error,
  authorNames = {},
  onAdd,
}: CommentsPanelProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onAdd(trimmed);
      setText("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card space-y-3">
      <h2 className="text-lg font-semibold">Comments</h2>
      <div className="flex gap-2">
        <input
          className="input-field flex-1"
          placeholder="Add a comment..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSubmit();
          }}
        />
        <button
          type="button"
          disabled={busy || !text.trim()}
          onClick={handleSubmit}
          className="btn-primary"
        >
          {busy ? "Adding..." : "Add"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading ? (
        <p className="text-sm text-slate-400">Loading comments...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-400">No comments yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {items.map((c) => (
            <li key={c.id} className="py-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-slate-700">
                  {authorNames[c.author_id] || "User"}
                </span>
                <time className="text-xs text-slate-400">
                  {new Date(c.created_at).toLocaleString()}
                </time>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-slate-600">{c.comment}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
