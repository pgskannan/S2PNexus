"use client";

import { useState } from "react";
import { queryAgent, runP2PPipeline, extractErrorMessage } from "@/lib/api";
import type { AgentQueryResponse, P2PPipelineResponse } from "@/lib/types";

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

  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineResult, setPipelineResult] = useState<P2PPipelineResponse | null>(null);

  async function handleRunPipeline() {
    setPipelineLoading(true);
    setPipelineError(null);
    setPipelineResult(null);
    try {
      const response = await runP2PPipeline();
      setPipelineResult(response);
    } catch (err) {
      setPipelineError(extractErrorMessage(err));
    } finally {
      setPipelineLoading(false);
    }
  }

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

      <div className="card space-y-4">
        <div>
          <h2 className="text-lg font-semibold">P2P Multi-Agent Pipeline (Google ADK)</h2>
          <p className="mt-1 text-sm text-slate-500">
            Runs a 3-step sequential handoff on Google ADK — requisition intake →
            supplier/sourcing check → receipt/invoice match — each step grounded
            in live S2PNexus data and logged individually to Agent Activity below.
          </p>
        </div>

        <button
          type="button"
          onClick={handleRunPipeline}
          disabled={pipelineLoading}
          className="btn-primary"
        >
          {pipelineLoading ? "Running pipeline..." : "Run P2P pipeline"}
        </button>

        {pipelineError && <p className="text-sm text-red-600">{pipelineError}</p>}

        {pipelineResult && (
          <div className="space-y-3">
            <span
              className={`badge ${
                pipelineResult.success
                  ? "bg-green-100 text-green-700"
                  : "bg-amber-100 text-amber-700"
              }`}
            >
              {pipelineResult.success ? "all steps succeeded" : "one or more steps degraded"}
            </span>

            <ol className="space-y-3">
              {pipelineResult.steps.map((step, i) => (
                <li key={step.agent_name} className="rounded-md border border-slate-200 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium uppercase text-slate-400">
                      Step {i + 1} — {step.agent_name}
                    </span>
                    <span
                      className={`badge ${
                        step.success
                          ? "bg-green-100 text-green-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {step.success ? "ok" : "failed"} · {step.latency_ms}ms
                    </span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm text-slate-800">
                    {step.message}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}
