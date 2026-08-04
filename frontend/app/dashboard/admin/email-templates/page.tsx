"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  extractErrorMessage,
  listEmailTemplatesAdmin,
  upsertEmailTemplateAdmin,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type {
  EmailTemplateCatalogEntry,
  EmailTemplateOverrideUpsert,
} from "@/lib/types";

interface DraftForm {
  subject_override: string;
  html_override: string;
  footer_override: string;
  branding_logo_url: string;
  is_active: boolean;
}

function emptyDraft(entry?: EmailTemplateCatalogEntry): DraftForm {
  return {
    subject_override: entry?.subject_override || "",
    html_override: entry?.html_override || "",
    footer_override: entry?.footer_override || "",
    branding_logo_url: entry?.branding_logo_url || "",
    is_active: entry?.override_active !== false,
  };
}

function hasChanges(draft: DraftForm): boolean {
  return Boolean(
    draft.subject_override.trim() ||
      draft.html_override.trim() ||
      draft.footer_override.trim() ||
      draft.branding_logo_url.trim()
  );
}

function TemplateEditor({
  entry,
  onSaved,
}: {
  entry: EmailTemplateCatalogEntry;
  onSaved: (updated: EmailTemplateCatalogEntry) => void;
}) {
  const [draft, setDraft] = useState<DraftForm>(() => emptyDraft(entry));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  function patch(p: Partial<DraftForm>) {
    setDraft((d) => ({ ...d, ...p }));
  }

  async function save(reset: boolean) {
    setSaving(true);
    setError(null);
    try {
      const payload: EmailTemplateOverrideUpsert = reset
        ? {
            subject_override: null,
            html_override: null,
            footer_override: null,
            branding_logo_url: null,
            is_active: true,
          }
        : {
            subject_override: draft.subject_override.trim() || null,
            html_override: draft.html_override.trim() || null,
            footer_override: draft.footer_override.trim() || null,
            branding_logo_url: draft.branding_logo_url.trim() || null,
            is_active: draft.is_active,
          };
      const saved = await upsertEmailTemplateAdmin(entry.email_type, payload);
      const updated: EmailTemplateCatalogEntry = {
        ...entry,
        subject_override: saved.subject_override,
        html_override: saved.html_override,
        footer_override: saved.footer_override,
        branding_logo_url: saved.branding_logo_url,
        override_active: saved.is_active,
        has_override: true,
        updated_at: saved.updated_at,
      };
      onSaved(updated);
      if (reset) {
        setDraft(emptyDraft(updated));
      }
      setSavedAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const changed = hasChanges(draft);

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-slate-900">{entry.email_type}</h3>
          <p className="mt-0.5 text-sm text-slate-500">{entry.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
              changed && draft.is_active
                ? "bg-emerald-100 text-emerald-700"
                : draft.is_active
                  ? "bg-sky-100 text-sky-700"
                  : "bg-slate-100 text-slate-600"
            }`}
          >
            {changed && draft.is_active
              ? "Customized"
              : draft.is_active
                ? "Default"
                : "Disabled override"}
          </span>
          {savedAt && <span className="text-xs text-slate-400">Saved {savedAt}</span>}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Email subject
          </label>
          <input
            value={draft.subject_override}
            onChange={(e) => patch({ subject_override: e.target.value })}
            placeholder={entry.subject}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
          <p className="mt-1 text-xs text-slate-400">
            Default: <span className="font-mono">{entry.subject}</span>
          </p>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Email body (HTML)
          </label>
          <textarea
            value={draft.html_override}
            onChange={(e) => patch({ html_override: e.target.value })}
            rows={6}
            placeholder="Leave blank to use the default template body. Supports {{variable}} and {{#if}}/{{#each}} markup."
            className="w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Footer</label>
          <textarea
            value={draft.footer_override}
            onChange={(e) => patch({ footer_override: e.target.value })}
            rows={2}
            placeholder="Rendered into the {{tenant.footer}} slot of the template."
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            Branding logo URL
          </label>
          <input
            value={draft.branding_logo_url}
            onChange={(e) => patch({ branding_logo_url: e.target.value })}
            placeholder="https://… (rendered into the {{tenant.logo}} slot)"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            id={`active-${entry.email_type}`}
            type="checkbox"
            checked={draft.is_active}
            onChange={(e) => patch({ is_active: e.target.checked })}
            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
          />
          <label htmlFor={`active-${entry.email_type}`} className="text-sm text-slate-700">
            Override is active (uncheck to fall back to the default template)
          </label>
        </div>
      </div>

      {entry.variables.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
            Available variables
          </p>
          <div className="flex flex-wrap gap-1.5">
            {entry.variables.map((v) => (
              <span key={v} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">
                {`{{${v}}}`}
              </span>
            ))}
          </div>
        </div>
      )}

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
        <button
          onClick={() => save(false)}
          disabled={saving}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button
          onClick={() => save(true)}
          disabled={saving}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Reset to default
        </button>
      </div>
    </div>
  );
}

export default function EmailTemplatesAdminPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "administrator" || user?.is_superuser === true;

  const [items, setItems] = useState<EmailTemplateCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    listEmailTemplatesAdmin()
      .then((res) => setItems(res.items))
      .catch((e) => setError(extractErrorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const byModule = useMemo(() => {
    const groups = new Map<string, EmailTemplateCatalogEntry[]>();
    for (const item of items) {
      const list = groups.get(item.module) ?? [];
      list.push(item);
      groups.set(item.module, list);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  function updateEntry(updated: EmailTemplateCatalogEntry) {
    setItems((prev) => prev.map((item) => (item.email_type === updated.email_type ? updated : item)));
  }

  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        You need administrator access to configure email templates.
      </div>
    );
  }

  const selectedEntry = items.find((item) => item.email_type === selected) ?? null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Email Templates</h2>
        <p className="mt-1 text-sm text-slate-500">
          Configure lifecycle email content — subject, body, footer, and branding — per email type.
          Unset fields fall back to the system default template.
        </p>
      </div>

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-700">{error}</p>
          <button onClick={load} className="text-sm font-medium text-red-700 underline">
            Retry
          </button>
        </div>
      )}

      {loading && <p className="text-sm text-slate-500">Loading templates…</p>}

      {!loading && !error && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            {byModule.map(([module, entries]) => (
              <div key={module}>
                <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
                  {module}
                </h3>
                <div className="space-y-2">
                  {entries.map((entry) => {
                    const changed = Boolean(
                      entry.subject_override ||
                        entry.html_override ||
                        entry.footer_override ||
                        entry.branding_logo_url
                    );
                    return (
                      <button
                        key={entry.email_type}
                        onClick={() => setSelected(entry.email_type)}
                        className={`w-full rounded-lg border p-3 text-left transition-colors ${
                          selected === entry.email_type
                            ? "border-brand-500 bg-brand-50"
                            : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-sm font-medium text-slate-800">
                            {entry.email_type}
                          </span>
                          {changed && entry.override_active !== false && (
                            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                              Customized
                            </span>
                          )}
                          {entry.override_active === false && (
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
                              Override off
                            </span>
                          )}
                        </div>
                        <p className="mt-1 line-clamp-2 text-xs text-slate-500">{entry.description}</p>
                        <p className="mt-1 truncate font-mono text-xs text-slate-400">
                          {entry.subject_override || entry.subject}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div>
            {selectedEntry ? (
              <TemplateEditor key={selectedEntry.email_type} entry={selectedEntry} onSaved={updateEntry} />
            ) : (
              <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
                Select a template on the left to configure its subject, body, footer, and branding.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
