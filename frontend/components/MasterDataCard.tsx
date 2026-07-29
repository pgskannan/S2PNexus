"use client";

import { useEffect, useRef, useState } from "react";
import { extractErrorMessage } from "@/lib/api";

interface MasterDataCardProps {
  title: string;
  description: string;
  columnsHint: string;
  isAdmin: boolean;
  getCount: () => Promise<number>;
  upload: (file: File) => Promise<{ loaded: number; errors?: string[] }>;
  download?: () => Promise<void>;
  deleteAll: () => Promise<{ deleted: number }>;
}

export default function MasterDataCard({
  title,
  description,
  columnsHint,
  isAdmin,
  getCount,
  upload,
  download,
  deleteAll,
}: MasterDataCardProps) {
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
    if (!window.confirm(`Deactivate all ${title} data? Rows are marked inactive (not deleted) and drop out of pickers/lookups immediately.`)) {
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
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <p className="mt-2 text-sm text-slate-500">{description}</p>
          <p className="mt-2 text-xs text-slate-400">Expected CSV columns: {columnsHint}</p>
        </div>
        <div className="whitespace-nowrap text-sm text-slate-500">
          {loadingCount ? "Loading..." : `${count ?? 0} row(s)`}
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {success && <p className="mt-3 text-sm text-emerald-700">{success}</p>}
      {uploadErrors.length > 0 && (
        <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <p className="font-medium">{uploadErrors.length} row(s) skipped:</p>
          <ul className="mt-1 list-disc pl-4">
            {uploadErrors.slice(0, 10).map((errorMessage, index) => (
              <li key={index}>{errorMessage}</li>
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
          <button type="button" className="btn-primary" disabled={!file || uploading} onClick={handleUpload}>
            {uploading ? "Uploading..." : "Upload"}
          </button>
          {download && (
            <button type="button" className="btn-secondary" disabled={downloading} onClick={handleDownload}>
              {downloading ? "Downloading..." : "Download current"}
            </button>
          )}
          <button type="button" className="btn-secondary" disabled={deleting} onClick={handleDeleteAll}>
            {deleting ? "Deactivating..." : "Deactivate all"}
          </button>
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-500">Only administrators can upload, download, or deactivate master data.</p>
      )}
    </div>
  );
}
