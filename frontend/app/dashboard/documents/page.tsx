"use client";

import { useEffect, useState } from "react";
import { listDocuments, uploadDocument, deleteDocument, extractErrorMessage } from "@/lib/api";
import type { Document } from "@/lib/types";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const [items, setItems] = useState<Document[]>([]);
  const [search, setSearch] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listDocuments({ search: search || undefined });
      setItems(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!selectedFile) {
      setError("Please select a file to upload.");
      return;
    }

    setUploading(true);
    try {
      await uploadDocument(selectedFile, documentType || undefined);
      setSelectedFile(null);
      setDocumentType("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this document?")) return;
    setDeletingId(id);
    setError(null);
    try {
      await deleteDocument(id);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Documents</h1>
      </div>

      <form onSubmit={handleUpload} className="grid gap-3 sm:grid-cols-[1.5fr_auto]">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="flex flex-1 items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <span className="text-sm text-slate-500">Select file</span>
            <input
              type="file"
              className="block w-full text-sm text-slate-900 file:border-0 file:bg-slate-50 file:px-3 file:py-2 file:text-slate-700"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <input
            className="input-field max-w-xs"
            placeholder="Document type"
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={uploading}>
          {uploading ? "Uploading..." : "+ Upload Document"}
        </button>
      </form>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        className="flex gap-2"
      >
        <input
          className="input-field max-w-xs"
          placeholder="Search filename or type..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="btn-secondary">
          Search
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Filename</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={5}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={5}>
                  No documents yet.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-brand-700">
                  {item.filename}
                </td>
                <td className="px-4 py-3 text-slate-600">{item.document_type}</td>
                <td className="px-4 py-3 text-slate-600">{formatFileSize(item.file_size)}</td>
                <td className="px-4 py-3 text-slate-500">
                  {new Date(item.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => handleDelete(item.id)}
                    className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-red-600 hover:bg-slate-50"
                    disabled={deletingId === item.id}
                  >
                    {deletingId === item.id ? "Deleting..." : "Delete"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
