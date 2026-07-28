"use client";

import { useEffect, useState } from "react";
import {
  getPurchaseOrderLineItemSplits,
  setPurchaseOrderLineItemSplits,
  extractErrorMessage,
} from "@/lib/api";
import type { AccountingSplit } from "@/lib/types";

interface SplitRow {
  gl_account_code: string;
  percentage: string;
  amount: string;
  cost_center: string;
}

function emptyRow(): SplitRow {
  return { gl_account_code: "", percentage: "", amount: "", cost_center: "" };
}

function fromApi(splits: AccountingSplit[]): { method: "percentage" | "amount"; rows: SplitRow[] } {
  if (splits.length === 0) {
    return { method: "amount", rows: [emptyRow()] };
  }
  return {
    method: splits[0].split_method,
    rows: splits.map((s) => ({
      gl_account_code: s.gl_account_code,
      percentage: s.percentage ?? "",
      amount: s.amount ?? "",
      cost_center: s.cost_center ?? "",
    })),
  };
}

export default function AccountingSplitEditor({
  purchaseOrderId,
  lineItemId,
  lineTotal,
}: {
  purchaseOrderId: string;
  lineItemId: string;
  lineTotal?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [method, setMethod] = useState<"percentage" | "amount">("amount");
  const [rows, setRows] = useState<SplitRow[]>([emptyRow()]);
  const [summaryLabel, setSummaryLabel] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const splits = await getPurchaseOrderLineItemSplits(purchaseOrderId, lineItemId);
      const { method: m, rows: r } = fromApi(splits);
      setMethod(m);
      setRows(r);
      setSummaryLabel(
        splits.length === 0
          ? "No split configured"
          : splits.length === 1
          ? splits[0].gl_account_code
          : `${splits.length} accounts`
      );
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    // Load the summary label eagerly (collapsed view still shows current GL
    // account), full row editing state is reused from the same fetch.
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateRow(index: number, patch: Partial<SplitRow>) {
    setRows((r) => r.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addRow() {
    setRows((r) => [...r, emptyRow()]);
  }

  function removeRow(index: number) {
    setRows((r) => r.filter((_, i) => i !== index));
  }

  async function handleSave() {
    setError(null);
    setSaving(true);
    try {
      const payload = rows
        .filter((r) => r.gl_account_code.trim())
        .map((r) => ({
          split_method: method,
          gl_account_code: r.gl_account_code,
          percentage: method === "percentage" ? r.percentage || "0" : undefined,
          amount: method === "amount" ? r.amount || "0" : undefined,
          cost_center: r.cost_center || undefined,
        }));
      const saved = await setPurchaseOrderLineItemSplits(purchaseOrderId, lineItemId, payload);
      setSummaryLabel(saved.length === 1 ? saved[0].gl_account_code : `${saved.length} accounts`);
      setExpanded(false);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="text-xs">
      <button
        type="button"
        className="text-brand-600 hover:underline"
        onClick={() => setExpanded((v) => !v)}
      >
        {loaded ? summaryLabel || "Set split" : "..."} {expanded ? "▲" : "▼"}
      </button>

      {expanded && (
        <div className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={method === "amount"}
                onChange={() => setMethod("amount")}
              />
              Amount
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={method === "percentage"}
                onChange={() => setMethod("percentage")}
              />
              Percentage
            </label>
            {lineTotal && method === "amount" && (
              <span className="text-slate-400">Line total: {lineTotal}</span>
            )}
          </div>

          {rows.map((row, index) => (
            <div key={index} className="flex items-center gap-2">
              <input
                className="input-field flex-1 py-1 text-xs"
                placeholder="GL account code"
                value={row.gl_account_code}
                onChange={(e) => updateRow(index, { gl_account_code: e.target.value })}
              />
              {method === "percentage" ? (
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  className="input-field w-20 py-1 text-xs"
                  placeholder="%"
                  value={row.percentage}
                  onChange={(e) => updateRow(index, { percentage: e.target.value })}
                />
              ) : (
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  className="input-field w-24 py-1 text-xs"
                  placeholder="Amount"
                  value={row.amount}
                  onChange={(e) => updateRow(index, { amount: e.target.value })}
                />
              )}
              <input
                className="input-field w-24 py-1 text-xs"
                placeholder="Cost center"
                value={row.cost_center}
                onChange={(e) => updateRow(index, { cost_center: e.target.value })}
              />
              <button
                type="button"
                className="text-red-600"
                onClick={() => removeRow(index)}
                disabled={rows.length === 1}
              >
                ✕
              </button>
            </div>
          ))}

          <div className="flex items-center gap-3">
            <button type="button" className="text-brand-600 hover:underline" onClick={addRow}>
              + Add account
            </button>
            <button
              type="button"
              className="btn-primary py-1 text-xs"
              disabled={saving}
              onClick={handleSave}
            >
              {saving ? "Saving..." : "Save split"}
            </button>
          </div>
          <p className="text-slate-400">
            {method === "percentage"
              ? "Percentages must sum to exactly 100."
              : "Amounts must sum to exactly the line total."}
          </p>
          {error && <p className="text-red-600">{error}</p>}
        </div>
      )}
    </div>
  );
}
