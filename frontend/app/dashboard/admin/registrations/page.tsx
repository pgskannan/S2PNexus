"use client";

/**
 * SLP Admin registration console — send / download / upload Excel workbooks.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePagination } from "@/components/Pagination";
import Pagination from "@/components/Pagination";
import {
  downloadRegistrationErrorReport,
  downloadRegistrationWorkbook,
  extractErrorMessage,
  importRegistrationWorkbook,
  listSupplierRegistrations,
  sendSupplierRegistration,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import type {
  ImportValidationFailure,
  SupplierRegistrationSummary,
} from "@/lib/types";

export default function RegistrationsAdminPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "administrator" || user?.role === "supplier_manager";

  const [rows, setRows] = useState<SupplierRegistrationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [failures, setFailures] = useState<ImportValidationFailure[] | null>(null);
  const [failureRegId, setFailureRegId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = useState<string | null>(null);

  const { pageItems, page, setPage, totalPages, pageSize } = usePagination(rows, 10);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listSupplierRegistrations({ limit: 500 });
      setRows(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleSend(id: string) {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      await sendSupplierRegistration(id);
      setNotice("Registration workbook sent.");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDownload(id: string, number: string) {
    setBusyId(id);
    setError(null);
    try {
      const blob = await downloadRegistrationWorkbook(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${number}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  function promptUpload(id: string) {
    setUploadTarget(id);
    fileRef.current?.click();
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const id = uploadTarget;
    e.target.value = "";
    setUploadTarget(null);
    if (!file || !id) return;
    setBusyId(id);
    setError(null);
    setNotice(null);
    setFailures(null);
    try {
      const result = await importRegistrationWorkbook(id, file);
      if (result.ok) {
        setNotice(
          `Import succeeded — grade ${result.registration?.grade ?? "—"}, ` +
            `qualification=${result.registration?.qualification_status ?? "—"}.`
        );
        await load();
      } else {
        setFailures(result.failures);
        setFailureRegId(id);
        setError(result.import_summary || "Import failed validation.");
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function downloadErrors() {
    if (!failureRegId) return;
    try {
      const blob = await downloadRegistrationErrorReport(failureRegId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "ErrorReport.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Supplier Registrations</h1>
        <p className="mt-1 text-sm text-slate-500">
          Excel registration status, send/download, and import for SLP Admins.
        </p>
      </div>

      {!isAdmin && (
        <div className="card border border-amber-200 bg-amber-50 text-sm text-amber-800">
          Import is restricted to SLP Admin. You can still view status.
        </div>
      )}
      {error && <div className="card border border-red-200 bg-red-50 text-sm text-red-700 whitespace-pre-wrap">{error}</div>}
      {notice && <div className="card border border-green-200 bg-green-50 text-sm text-green-700">{notice}</div>}

      <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => void onFileChosen(e)} />

      <div className="card overflow-x-auto">
        {loading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          <>
            <table className="min-w-full text-left text-sm">
              <thead className="border-b text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-3">Number</th>
                  <th className="py-2 pr-3">Company</th>
                  <th className="py-2 pr-3">Mode</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Score</th>
                  <th className="py-2 pr-3">Sent</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((row) => (
                  <tr key={row.id} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-mono text-xs">{row.registration_number}</td>
                    <td className="py-2 pr-3">{row.company_name}</td>
                    <td className="py-2 pr-3 uppercase text-xs">{row.registration_mode || "—"}</td>
                    <td className="py-2 pr-3">{row.status}</td>
                    <td className="py-2 pr-3">
                      {row.total_score != null ? `${row.total_score} (${row.grade ?? "—"})` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-xs text-slate-500">
                      {row.workbook_sent_at ? new Date(row.workbook_sent_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="py-2 space-x-2 whitespace-nowrap">
                      {(row.registration_mode === "manual" || row.status === "pending_registration") && (
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          disabled={!!busyId}
                          onClick={() => void handleSend(row.id)}
                        >
                          Send
                        </button>
                      )}
                      {row.workbook_sent_at && (
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          disabled={!!busyId}
                          onClick={() => void handleDownload(row.id, row.registration_number)}
                        >
                          Download
                        </button>
                      )}
                      {isAdmin && row.workbook_sent_at && (
                        <button
                          type="button"
                          className="btn-primary text-xs"
                          disabled={!!busyId}
                          onClick={() => promptUpload(row.id)}
                        >
                          Upload
                        </button>
                      )}
                      {row.supplier_id && (
                        <Link
                          href={`/dashboard/suppliers/${row.supplier_id}`}
                          className="text-xs text-slate-600 underline"
                        >
                          Supplier
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
                {!pageItems.length && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-slate-500">
                      No registrations yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <Pagination
              page={page}
              totalPages={totalPages}
              totalItems={rows.length}
              pageSize={pageSize}
              onPageChange={setPage}
            />
          </>
        )}
      </div>

      {failures && failures.length > 0 && (
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium">Import validation failures</h2>
            {failureRegId && (
              <button type="button" className="btn-secondary text-xs" onClick={() => void downloadErrors()}>
                Download ErrorReport.xlsx
              </button>
            )}
          </div>
          <table className="min-w-full text-left text-sm">
            <thead className="border-b text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3">Category</th>
                <th className="py-2 pr-3">Sheet</th>
                <th className="py-2 pr-3">Cell</th>
                <th className="py-2 pr-3">Rule</th>
                <th className="py-2 pr-3">Expected</th>
                <th className="py-2">Actual</th>
              </tr>
            </thead>
            <tbody>
              {failures.map((f, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-mono text-xs">{f.category}</td>
                  <td className="py-2 pr-3">{f.sheet}</td>
                  <td className="py-2 pr-3">{f.cell || "—"}</td>
                  <td className="py-2 pr-3">{f.rule}</td>
                  <td className="py-2 pr-3 text-xs">{f.expected || "—"}</td>
                  <td className="py-2 text-xs">{f.actual || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
