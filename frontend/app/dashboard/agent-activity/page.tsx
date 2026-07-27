"use client";

import { Fragment, useEffect, useState } from "react";
import {
  listAgentActivity,
  getAgentActivitySummary,
  extractErrorMessage,
} from "@/lib/api";
import type {
  AgentActivityLogEntry,
  AgentActivitySummaryResponse,
} from "@/lib/types";

const PAGE_SIZE = 25;

export default function AgentActivityPage() {
  const [items, setItems] = useState<AgentActivityLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [agentFilter, setAgentFilter] = useState("");
  const [successFilter, setSuccessFilter] = useState<"" | "true" | "false">("");
  const [summary, setSummary] = useState<AgentActivitySummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function load(nextOffset = offset) {
    setLoading(true);
    setError(null);
    try {
      const [logRes, summaryRes] = await Promise.all([
        listAgentActivity({
          agent_name: agentFilter || undefined,
          success: successFilter === "" ? undefined : successFilter === "true",
          limit: PAGE_SIZE,
          offset: nextOffset,
        }),
        getAgentActivitySummary(),
      ]);
      setItems(logRes.items);
      setTotal(logRes.total);
      setOffset(nextOffset);
      setSummary(summaryRes);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Agent Activity</h1>
        <p className="mt-1 text-sm text-slate-500">
          Read-only audit trail of every AI agent invocation -- which agent
          answered, what tools grounded the response, and whether a live LLM
          call produced it.
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="card">
            <p className="text-xs uppercase text-slate-400">Total calls</p>
            <p className="mt-1 text-2xl font-semibold">{summary.total_calls}</p>
          </div>
          <div className="card">
            <p className="text-xs uppercase text-slate-400">Success rate</p>
            <p className="mt-1 text-2xl font-semibold">
              {summary.total_calls > 0
                ? `${Math.round((summary.success_count / summary.total_calls) * 100)}%`
                : "—"}
            </p>
          </div>
          <div className="card">
            <p className="text-xs uppercase text-slate-400">LLM-generated</p>
            <p className="mt-1 text-2xl font-semibold">{summary.llm_used_count}</p>
          </div>
          <div className="card">
            <p className="text-xs uppercase text-slate-400">Agents used</p>
            <p className="mt-1 text-2xl font-semibold">
              {Object.keys(summary.by_agent).length}
            </p>
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(0);
        }}
        className="flex flex-wrap gap-2"
      >
        <input
          className="input-field max-w-xs"
          placeholder="Filter by agent name..."
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
        />
        <select
          className="input-field max-w-[10rem]"
          value={successFilter}
          onChange={(e) => setSuccessFilter(e.target.value as "" | "true" | "false")}
        >
          <option value="">All outcomes</option>
          <option value="true">Success only</option>
          <option value="false">Failure only</option>
        </select>
        <button type="submit" className="btn-secondary">
          Filter
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card overflow-x-auto p-0">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Timestamp</th>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Request</th>
              <th className="px-4 py-3">Tools used</th>
              <th className="px-4 py-3">LLM</th>
              <th className="px-4 py-3">Outcome</th>
              <th className="px-4 py-3">Latency</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={7}>
                  Loading...
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td className="px-4 py-4 text-slate-400" colSpan={7}>
                  No agent activity recorded yet. Ask the AI Agent something
                  to generate the first entry.
                </td>
              </tr>
            )}
            {items.map((item) => (
              <Fragment key={item.id}>
                <tr
                  className="cursor-pointer hover:bg-slate-50"
                  onClick={() =>
                    setExpandedId(expandedId === item.id ? null : item.id)
                  }
                >
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                    {new Date(item.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className="badge bg-brand-50 text-brand-700">
                      {item.agent_name}
                    </span>
                  </td>
                  <td className="max-w-xs truncate px-4 py-3">
                    {item.request_text}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {item.tools_used.length > 0
                      ? item.tools_used.join(", ")
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`badge ${
                        item.llm_used
                          ? "bg-purple-100 text-purple-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {item.llm_used ? "live" : "templated"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`badge ${
                        item.success
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {item.success ? "handled" : "unhandled"}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                    {item.latency_ms != null ? `${item.latency_ms} ms` : "—"}
                  </td>
                </tr>
                {expandedId === item.id && (
                  <tr>
                    <td colSpan={7} className="bg-slate-50 px-4 py-4">
                      <div className="space-y-3">
                        <div>
                          <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                            Response message
                          </p>
                          <p className="whitespace-pre-wrap text-sm text-slate-800">
                            {item.message}
                          </p>
                        </div>
                        {item.explanation && (
                          <div>
                            <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                              Explanation
                            </p>
                            <p className="text-sm text-slate-600">
                              {item.explanation}
                            </p>
                          </div>
                        )}
                        {item.plan.length > 0 && (
                          <div>
                            <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                              Agent plan
                            </p>
                            <ol className="list-inside list-decimal space-y-1 text-sm text-slate-600">
                              {item.plan.map((step, i) => (
                                <li key={i}>{String(step)}</li>
                              ))}
                            </ol>
                          </div>
                        )}
                        <div>
                          <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                            Raw response data
                          </p>
                          <pre className="max-h-64 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                            {JSON.stringify(item.data, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>
          {total > 0
            ? `Showing ${offset + 1}-${Math.min(offset + PAGE_SIZE, total)} of ${total}`
            : "No results"}
        </span>
        <div className="flex gap-2">
          <button
            className="btn-secondary"
            disabled={!canPrev || loading}
            onClick={() => load(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            className="btn-secondary"
            disabled={!canNext || loading}
            onClick={() => load(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
