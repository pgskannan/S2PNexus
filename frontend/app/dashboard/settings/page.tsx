"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import { extractErrorMessage, getAiProvider, updateAiProvider } from "@/lib/api";

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
    </div>
  );
}
