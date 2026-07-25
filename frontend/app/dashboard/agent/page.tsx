"use client";

import { useState } from "react";
import { queryAgent, extractErrorMessage } from "@/lib/api";
import type { AgentQueryResponse } from "@/lib/types";

const suggestions = [
  "Show me all open requisitions over $5,000",
  "Which suppliers do we have on file?",
  "Summarize spend by category this quarter",
  "What's the status of our active sourcing events?",
];

export default function AgentPage() {
  const [request, setRequest] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentQueryResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!request.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await queryAgent(request);
      setResult(response);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">AI Agent</h1>
        <p className="mt-1 text-sm text-slate-500">
          Ask a question in plain language. The orchestrator routes it to the
          right domain agent and grounds the answer in live S2PNexus data.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card space-y-4">
        <textarea
          className="input-field"
          rows={3}
          placeholder="e.g. What requisitions need my approval?"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setRequest(s)}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:border-brand-300 hover:text-brand-700"
            >
              {s}
            </button>
          ))}
        </div>
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "Thinking..." : "Ask agent"}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {result && (
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <span className="badge bg-brand-50 text-brand-700">
              {result.agent_name}
            </span>
            <span
              className={`badge ${
                result.success
                  ? "bg-green-100 text-green-700"
                  : "bg-red-100 text-red-700"
              }`}
            >
              {result.success ? "handled" : "unhandled"}
            </span>
          </div>

          <p className="whitespace-pre-wrap text-sm text-slate-800">
            {result.message}
          </p>

          {result.plan.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                Agent plan
              </p>
              <ol className="list-inside list-decimal space-y-1 text-sm text-slate-600">
                {result.plan.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </div>
          )}

          {result.explanation && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                Explanation
              </p>
              <p className="text-sm text-slate-600">{result.explanation}</p>
            </div>
          )}

          {Object.keys(result.data).length > 0 && (
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">
                Data
              </p>
              <pre className="max-h-64 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-slate-100">
                {JSON.stringify(result.data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
