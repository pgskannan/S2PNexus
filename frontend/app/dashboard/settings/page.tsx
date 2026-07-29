"use client";

import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import {
  extractErrorMessage,
  getAiProvider,
  updateAiProvider,
  listDocumentNumberingFormats,
  updateDocumentNumberingFormat,
  previewDocumentNumberingFormat,
  getCommodityCodeCount,
  uploadCommodityCodes,
  downloadCommodityCodes,
  deleteAllCommodityCodes,
  getGlAccountCount,
  uploadGlAccounts,
  downloadGlAccounts,
  deleteAllGlAccounts,
  getCommodityGlMappingCount,
  uploadCommodityGlMapping,
  downloadCommodityGlMapping,
  deleteAllCommodityGlMapping,
} from "@/lib/api";
import type { DocumentNumberingFormat, DocumentType, ResetCadence } from "@/lib/types";

const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  procurement_requisition: "Requisitions (PR)",
  purchase_order: "Purchase Orders (PO)",
  goods_receipt: "Goods Receipts",
  procurement_invoice: "Invoices",
};

// Mirrors the token-substitution logic in app.crud.document_numbering.render_pattern
// so the form can show an instant preview without a round-trip on every keystroke.
// The authoritative "real next number" still comes from the preview endpoint.
function clientRenderPattern(pattern: string, prefix: string, padding: number): string {
  const now = new Date();
  const yyyy = String(now.getFullYear()).padStart(4, "0");
  const yy = String(now.getFullYear() % 100).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const seq = String(1).padStart(padding, "0");
  return pattern
    .replaceAll("{prefix}", prefix)
    .replaceAll("{yyyy}", yyyy)
    .replaceAll("{yy}", yy)
    .replaceAll("{mm}", mm)
    .replaceAll("{seq}", seq);
}

interface EditState {
  prefix: string;
  pattern: string;
  sequence_padding: number;
  reset_cadence: ResetCadence;
}

function DocumentNumberingSettings({ isAdmin }: { isAdmin: boolean }) {
  const [formats, setFormats] = useState<DocumentNumberingFormat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingType, setEditingType] = useState<DocumentType | null>(null);
  const [editState, setEditState] = useState<EditState | null>(null);
  const [realNextNumber, setRealNextNumber] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listDocumentNumberingFormats();
      setFormats(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startEditing(item: DocumentNumberingFormat) {
    setEditingType(item.document_type);
    setEditState({
      prefix: item.prefix,
      pattern: item.pattern,
      sequence_padding: item.sequence_padding,
      reset_cadence: item.reset_cadence,
    });
    setRealNextNumber(null);
    setError(null);
  }

  async function handlePreview() {
    if (!editingType || !editState) return;
    try {
      const res = await previewDocumentNumberingFormat({
        document_type: editingType,
        ...editState,
      });
      setRealNextNumber(res.next_number);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  async function handleSave() {
    if (!editingType || !editState) return;
    setSaving(true);
    setError(null);
    try {
      await updateDocumentNumberingFormat(editingType, editState);
      setEditingType(null);
      setEditState(null);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <div>
        <h2 className="text-lg font-semibold">Document Numbering</h2>
        <p className="mt-1 text-sm text-slate-500">
          Control the format of auto-generated document numbers, e.g.{" "}
          <span className="font-mono">PR2026-07-001</span>. Tokens: {"{prefix} {yyyy} {yy} {mm} {seq}"}.
        </p>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {loading && <p className="mt-3 text-sm text-slate-400">Loading...</p>}

      {!loading && (
        <div className="mt-4 divide-y divide-slate-100">
          {formats.map((item) => (
            <div key={item.document_type} className="py-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-800">
                    {DOCUMENT_TYPE_LABELS[item.document_type]}
                  </p>
                  <p className="mt-1 font-mono text-sm text-brand-700">{item.sample}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {item.pattern} &middot; pad {item.sequence_padding} &middot; resets {item.reset_cadence}
                    {item.is_customized ? " · customized" : " · default"}
                  </p>
                </div>
                {isAdmin && editingType !== item.document_type && (
                  <button className="btn-secondary" onClick={() => startEditing(item)}>
                    Edit
                  </button>
                )}
              </div>

              {isAdmin && editingType === item.document_type && editState && (
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="label">Prefix</label>
                      <input
                        className="input-field"
                        value={editState.prefix}
                        onChange={(e) => setEditState({ ...editState, prefix: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="label">Sequence padding</label>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        className="input-field"
                        value={editState.sequence_padding}
                        onChange={(e) =>
                          setEditState({ ...editState, sequence_padding: Number(e.target.value) || 1 })
                        }
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="label">Pattern</label>
                      <input
                        className="input-field font-mono"
                        value={editState.pattern}
                        onChange={(e) => setEditState({ ...editState, pattern: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="label">Resets</label>
                      <select
                        className="input-field"
                        value={editState.reset_cadence}
                        onChange={(e) =>
                          setEditState({ ...editState, reset_cadence: e.target.value as ResetCadence })
                        }
                      >
                        <option value="monthly">Monthly</option>
                        <option value="yearly">Yearly</option>
                        <option value="never">Never</option>
                      </select>
                    </div>
                  </div>

                  <div className="mt-4 rounded border border-slate-200 bg-white px-3 py-2 text-sm">
                    <span className="text-slate-500">Sample:</span>{" "}
                    <span className="font-mono text-brand-700">
                      {clientRenderPattern(editState.pattern, editState.prefix, editState.sequence_padding)}
                    </span>
                    {realNextNumber && (
                      <span className="ml-4 text-slate-500">
                        Real next number:{" "}
                        <span className="font-mono text-brand-700">{realNextNumber}</span>
                      </span>
                    )}
                  </div>

                  <div className="mt-4 flex items-center gap-3">
                    <button type="button" className="btn-secondary" onClick={handlePreview}>
                      Preview real next number
                    </button>
                    <button type="button" className="btn-primary" onClick={handleSave} disabled={saving}>
                      {saving ? "Saving..." : "Save"}
                    </button>
                    <button
                      type="button"
                      className="text-sm text-slate-500 hover:underline"
                      onClick={() => {
                        setEditingType(null);
                        setEditState(null);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface MasterDataCardProps {
  title: string;
  description: string;
  columnsHint: string;
  isAdmin: boolean;
  getCount: () => Promise<number>;
  upload: (file: File) => Promise<{ loaded: number; errors?: string[] }>;
  // Optional: not every master-data dataset has an export endpoint yet
  // (only commodity codes / GL accounts / mapping do, as of this pass).
  download?: () => Promise<void>;
  deleteAll: () => Promise<{ deleted: number }>;
}

function MasterDataCard({ title, description, columnsHint, isAdmin, getCount, upload, download, deleteAll }: MasterDataCardProps) {
  const [count, setCount] = useState<number | null>(null);
  const [loadingCount, setLoadingCount] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function refreshCount() {
    setLoadingCount(true);
    try {
      setCount(await getCount());
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoadingCount(false);
    }
  }

  useEffect(() => {
    refreshCount();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    setUploadErrors([]);
    try {
      const result = await upload(file);
      setSuccess(`Loaded ${result.loaded} row(s).`);
      if (result.errors && result.errors.length > 0) {
        setUploadErrors(result.errors);
      }
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refreshCount();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleDownload() {
    if (!download) return;
    setDownloading(true);
    setError(null);
    try {
      await download();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  }

  async function handleDeleteAll() {
    if (
      !window.confirm(
        `Deactivate all ${title} data? Rows are marked inactive (not deleted) and drop out of pickers/lookups immediately. Re-uploading the same codes later reactivates them.`
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await deleteAll();
      setSuccess(`Deactivated ${result.deleted} row(s).`);
      await refreshCount();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold">{title}</h3>
          <p className="mt-1 text-sm text-slate-500">{description}</p>
          <p className="mt-1 text-xs text-slate-400">Expected CSV columns: {columnsHint}</p>
        </div>
        <div className="whitespace-nowrap text-sm text-slate-500">
          {loadingCount ? "Loading..." : `${count ?? 0} row(s)`}
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {success && <p className="mt-3 text-sm text-green-600">{success}</p>}
      {uploadErrors.length > 0 && (
        <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <p className="font-medium">{uploadErrors.length} row(s) skipped:</p>
          <ul className="mt-1 list-disc pl-4">
            {uploadErrors.slice(0, 10).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
          {uploadErrors.length > 10 && <p className="mt-1">...and {uploadErrors.length - 10} more.</p>}
        </div>
      )}

      {isAdmin ? (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm text-slate-600 file:mr-3 file:rounded file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200"
          />
          <button
            type="button"
            className="btn-primary"
            disabled={!file || uploading}
            onClick={handleUpload}
          >
            {uploading ? "Uploading..." : "Upload"}
          </button>
          {download && (
            <button
              type="button"
              className="btn-secondary"
              disabled={downloading}
              onClick={handleDownload}
            >
              {downloading ? "Downloading..." : "Download current"}
            </button>
          )}
          <button
            type="button"
            className="btn-secondary"
            disabled={deleting}
            onClick={handleDeleteAll}
          >
            {deleting ? "Deactivating..." : "Deactivate all"}
          </button>
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Only administrators can upload, download, or deactivate master data.</p>
      )}
    </div>
  );
}

function MasterDataSettings({ isAdmin }: { isAdmin: boolean }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Master Data</h2>
        <p className="mt-1 text-sm text-slate-500">
          Load or reset the commodity code taxonomy, GL account chart of accounts, and the mapping
          between them. Load GL Accounts before Commodity-to-GL Mapping -- the mapping upload
          validates each row&apos;s GL account code against accounts already loaded.
        </p>
      </div>

      <MasterDataCard
        title="Commodity Codes"
        description="The commodity/UNSPSC-style taxonomy used for requisition line items and the commodity picker."
        columnsHint="Segment, Segment Title, Family, Family Title, Class, Class Title, Commodity, Commodity Title"
        isAdmin={isAdmin}
        getCount={async () => (await getCommodityCodeCount()).count}
        upload={uploadCommodityCodes}
        download={downloadCommodityCodes}
        deleteAll={deleteAllCommodityCodes}
      />

      <MasterDataCard
        title="GL Accounts"
        description="Your chart of accounts. Commodity-to-GL mappings reference these by code."
        columnsHint="code, description, account_type"
        isAdmin={isAdmin}
        getCount={async () => (await getGlAccountCount()).count}
        upload={uploadGlAccounts}
        download={downloadGlAccounts}
        deleteAll={deleteAllGlAccounts}
      />

      <MasterDataCard
        title="Commodity-to-GL Mapping"
        description="Default GL account (and optional cost center) per commodity segment/family/class/code."
        columnsHint="scope_level (segment|family|class|commodity), scope_code, gl_account_code, cost_center"
        isAdmin={isAdmin}
        getCount={getCommodityGlMappingCount}
        upload={uploadCommodityGlMapping}
        download={downloadCommodityGlMapping}
        deleteAll={deleteAllCommodityGlMapping}
      />
    </div>
  );
}

export default function SettingsPage() {
  const user = useAuthStore((state) => state.user);
  const [provider, setProvider] = useState<string>("");
  const [availableProviders, setAvailableProviders] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function loadProvider() {
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await getAiProvider();
      setProvider(data.current_provider);
      setAvailableProviders(data.available_providers);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProvider();
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await updateAiProvider(provider);
      setProvider(data.current_provider);
      setAvailableProviders(data.available_providers);
      setSuccess("Provider updated successfully.");
    } catch (err) {
      const message = extractErrorMessage(err);
      setError(message === "Only administrators can change this" ? message : message);
    } finally {
      setSaving(false);
    }
  }

  const isAdmin = user?.role === "administrator";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">
          Manage the active AI provider for this workspace.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {success && <p className="text-sm text-green-600">{success}</p>}

      <div className="card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm text-slate-500">Current provider</p>
            <p className="mt-2 text-2xl font-semibold capitalize">{loading ? "Loading..." : provider}</p>
          </div>
          {!isAdmin && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium uppercase tracking-wide text-slate-600">
              Read only
            </span>
          )}
        </div>

        <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
          {isAdmin ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="text-sm font-medium text-slate-700">Select provider</label>
                <div className="mt-3 space-y-2">
                  {availableProviders.map((option) => (
                    <label key={option} className="flex items-center gap-3 rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                      <input
                        type="radio"
                        name="provider"
                        value={option}
                        checked={provider === option}
                        onChange={(event) => setProvider(event.target.value)}
                        className="h-4 w-4 border-slate-300 text-brand-600"
                      />
                      <span className="capitalize">{option}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button type="submit" className="btn-primary" disabled={saving || loading}>
                  {saving ? "Saving..." : "Save provider"}
                </button>
                <button type="button" onClick={loadProvider} className="btn-secondary">
                  Refresh
                </button>
              </div>
            </form>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-slate-600">
                You can view the current provider, but only administrators can change it.
              </p>
              <div className="rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                <span className="font-medium">Current selection:</span> <span className="capitalize">{provider}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <DocumentNumberingSettings isAdmin={isAdmin} />
      <MasterDataSettings isAdmin={isAdmin} />
    </div>
  );
}
