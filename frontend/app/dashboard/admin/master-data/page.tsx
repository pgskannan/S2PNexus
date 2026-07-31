"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import {
  extractErrorMessage,
  getAiProvider,
  getCommodityCodeCount,
  getGlAccountCount,
  getCommodityGlMappingCount,
  getDepartmentsCount,
  getCostCentersCount,
  getPlantsCount,
  uploadCommodityCodes,
  downloadCommodityCodes,
  deleteAllCommodityCodes,
  uploadGlAccounts,
  downloadGlAccounts,
  deleteAllGlAccounts,
  uploadCommodityGlMapping,
  downloadCommodityGlMapping,
  deleteAllCommodityGlMapping,
  getCommodityMatchingPolicyCount,
  uploadCommodityMatchingPolicy,
  downloadCommodityMatchingPolicy,
  deleteAllCommodityMatchingPolicy,
  uploadDepartments,
  downloadDepartments,
  deleteAllDepartments,
  uploadCostCenters,
  downloadCostCenters,
  deleteAllCostCenters,
  uploadPlants,
  downloadPlants,
  deleteAllPlants,
  updateAiProvider,
  listDocumentNumberingFormats,
  updateDocumentNumberingFormat,
  previewDocumentNumberingFormat,
} from "@/lib/api";
import type {
  DocumentNumberingFormat,
  DocumentType,
  ResetCadence,
} from "@/lib/types";
import MasterDataCard from "@/components/MasterDataCard";

const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  procurement_requisition: "Requisitions (PR)",
  purchase_order: "Purchase Orders (PO)",
  goods_receipt: "Goods Receipts",
  procurement_invoice: "Invoices",
};

function clientRenderPattern(pattern: string, prefix: string, padding: number): string {
  const now = new Date();
  const yyyy = String(now.getFullYear()).padStart(4, "0");
  const yy = String(now.getFullYear() % 100).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  return pattern
    .replaceAll("{prefix}", prefix)
    .replaceAll("{yyyy}", yyyy)
    .replaceAll("{yy}", yy)
    .replaceAll("{mm}", mm)
    .replaceAll("{seq}", String(1).padStart(padding, "0"));
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
          Control the format of auto-generated document numbers, e.g. <span className="font-mono">PR2026-07-001</span>.
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
                  <p className="text-sm font-medium text-slate-800">{DOCUMENT_TYPE_LABELS[item.document_type]}</p>
                  <p className="mt-1 font-mono text-sm text-brand-700">{item.sample}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {item.pattern} · pad {item.sequence_padding} · resets {item.reset_cadence}
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
                        Real next number: <span className="font-mono text-brand-700">{realNextNumber}</span>
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

export default function MasterDataAdminPage() {
  const user = useAuthStore((state) => state.user);
  const [provider, setProvider] = useState<string>("");
  const [availableProviders, setAvailableProviders] = useState<string[]>([]);
  const [loadingProvider, setLoadingProvider] = useState(true);
  const [savingProvider, setSavingProvider] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const isAdmin = user?.role === "administrator";

  async function loadProvider() {
    setLoadingProvider(true);
    setError(null);
    try {
      const data = await getAiProvider();
      setProvider(data.current_provider);
      setAvailableProviders(data.available_providers);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoadingProvider(false);
    }
  }

  useEffect(() => {
    loadProvider();
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) return;
    setSavingProvider(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await updateAiProvider(provider);
      setProvider(data.current_provider);
      setAvailableProviders(data.available_providers);
      setSuccess("Provider updated successfully.");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSavingProvider(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Master Data Hub</h2>
        <p className="mt-1 text-sm text-slate-500">
          Manage master-data upload and export for commodity codes, GL accounts, org structure, AI provider, and document numbering.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {success && <p className="text-sm text-emerald-700">{success}</p>}

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="card">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm text-slate-500">Current provider</p>
              <p className="mt-2 text-2xl font-semibold capitalize">{loadingProvider ? "Loading..." : provider}</p>
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
                  <button type="submit" className="btn-primary" disabled={savingProvider || loadingProvider}>
                    {savingProvider ? "Saving..." : "Save provider"}
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

        <div className="card">
          <h3 className="text-base font-semibold text-slate-900">Document Numbering</h3>
          <p className="mt-2 text-sm text-slate-500">
            Manage numbering formats for requisitions, purchase orders, receipts, and invoices.
          </p>
          <div className="mt-4">
            <DocumentNumberingSettings isAdmin={isAdmin} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
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
          title="Categories"
          description="Requisition categories used for spend classification and reporting."
          columnsHint="code, name"
          isAdmin={isAdmin}
          getCount={async (): Promise<number> => {
            const data = await fetch('/api/v1/categories/master-data/count').then((r) => r.json().catch(() => ({ count: 0 })));
            return (data as any).count;
          }}
          upload={async (file: File) => {
            const form = new FormData();
            form.append("file", file);
            const res = await fetch("/api/v1/categories/master-data/upload", { method: "POST", body: form });
            const data = await res.json().catch(() => ({}));
            return (data as any) || { loaded: 0 };
          }}
          download={async (): Promise<void> => {
            const r = await fetch('/api/v1/categories/master-data/export');
            const blob = await r.blob();
            const text = await blob.text();
            // MasterDataCard expects a void-returning download that triggers client behavior;
            // use a simple client-side download here.
            const blobOut = new Blob([text], { type: 'text/csv' });
            const url = URL.createObjectURL(blobOut);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'categories.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
          }}
          deleteAll={async () => {
            const res = await fetch('/api/v1/categories/master-data', { method: 'DELETE' });
            const data = await res.json().catch(() => ({ deleted: 0 }));
            return data as { deleted: number };
          }}
        />

        <MasterDataCard
          title="Commodity-to-GL Mapping"
          description="Default GL account and optional cost center per commodity scope."
          columnsHint="scope_level, scope_code, gl_account_code, cost_center"
          isAdmin={isAdmin}
          getCount={getCommodityGlMappingCount}
          upload={uploadCommodityGlMapping}
          download={downloadCommodityGlMapping}
          deleteAll={deleteAllCommodityGlMapping}
        />

        <MasterDataCard
          title="Matching Policy"
          description="Two-way vs. three-way match per commodity scope, and when receipts auto-generate: always (auto_receive) and/or for line items at or under a price threshold. Two-way scopes never get a receipt at all -- their invoice matches straight against the PO. Drives receipt creation when a PO reaches Ordered status."
          columnsHint="scope_level, scope_code, required_match_type (two_way/three_way), auto_receive (true/false), auto_receive_price_threshold"
          isAdmin={isAdmin}
          getCount={getCommodityMatchingPolicyCount}
          upload={uploadCommodityMatchingPolicy}
          download={downloadCommodityMatchingPolicy}
          deleteAll={deleteAllCommodityMatchingPolicy}
        />

        <MasterDataCard
          title="Departments"
          description="Department master data used for organizational cost and approval structures."
          columnsHint="code, name, parent_department_id, is_active"
          isAdmin={isAdmin}
          getCount={async () => (await getDepartmentsCount()).count}
          upload={uploadDepartments}
          download={downloadDepartments}
          deleteAll={deleteAllDepartments}
        />

        <MasterDataCard
          title="Cost Centers"
          description="Cost center master data used for budget and accounting allocation."
          columnsHint="code, name, department_id, is_active"
          isAdmin={isAdmin}
          getCount={async () => (await getCostCentersCount()).count}
          upload={uploadCostCenters}
          download={downloadCostCenters}
          deleteAll={deleteAllCostCenters}
        />

        <MasterDataCard
          title="Plants"
          description="Plant master data for physical sites and warehouse locations."
          columnsHint="code, name, address_line1, city, state_province, postal_code, country, tax_id, is_active"
          isAdmin={isAdmin}
          getCount={async () => (await getPlantsCount()).count}
          upload={uploadPlants}
          download={downloadPlants}
          deleteAll={deleteAllPlants}
        />
      </div>
    </div>
  );
}
