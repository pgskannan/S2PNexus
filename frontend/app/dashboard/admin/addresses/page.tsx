"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/auth-store";
import { createSharedAddress, deleteSharedAddress, extractErrorMessage, listSharedAddresses, updateSharedAddress } from "@/lib/api";
import type { AddressResult } from "@/lib/types";

interface AddressFormState {
  label: string;
  address_line1: string;
  city: string;
}

const emptyFormState = (): AddressFormState => ({ label: "", address_line1: "", city: "" });

export default function SharedAddressesAdminPage() {
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "administrator";
  const [items, setItems] = useState<AddressResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formState, setFormState] = useState<AddressFormState>(emptyFormState());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function loadAddresses() {
    setLoading(true);
    setError(null);
    try {
      const data = await listSharedAddresses();
      setItems(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAddresses();
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isAdmin) return;
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        label: formState.label,
        address_line1: formState.address_line1,
        city: formState.city,
      };
      if (editingId) {
        await updateSharedAddress(editingId, payload);
      } else {
        await createSharedAddress(payload);
      }
      setFormState(emptyFormState());
      setEditingId(null);
      await loadAddresses();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item: AddressResult) {
    if (!window.confirm(`Delete ${item.label}?`)) return;
    setError(null);
    try {
      await deleteSharedAddress(item.id);
      await loadAddresses();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  function startEditing(item: AddressResult) {
    setEditingId(item.id);
    setFormState({
      label: item.label,
      address_line1: item.address_line1 ?? "",
      city: item.city ?? "",
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Shared Address Book</h2>
        <p className="mt-1 text-sm text-slate-500">
          Maintain tenant-wide shared addresses for common receiving and billing destinations.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {!isAdmin && (
        <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          You can view the shared address list, but only administrators can add, edit, or remove addresses.
        </p>
      )}

      {isAdmin && (
        <div className="card space-y-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">{editingId ? "Edit address" : "Create address"}</h3>
            <p className="text-sm text-slate-500">Keep the tenant shared address book up to date.</p>
          </div>

          <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-3">
            <div>
              <label className="label">Label</label>
              <input className="input-field" value={formState.label} onChange={(event) => setFormState({ ...formState, label: event.target.value })} />
            </div>
            <div>
              <label className="label">Address line</label>
              <input className="input-field" value={formState.address_line1} onChange={(event) => setFormState({ ...formState, address_line1: event.target.value })} />
            </div>
            <div>
              <label className="label">City</label>
              <input className="input-field" value={formState.city} onChange={(event) => setFormState({ ...formState, city: event.target.value })} />
            </div>
            <div className="md:col-span-3 flex gap-3">
              <button className="btn-primary" type="submit" disabled={saving}>
                {saving ? "Saving..." : editingId ? "Save changes" : "Create address"}
              </button>
              {editingId && (
                <button className="btn-secondary" type="button" onClick={() => setEditingId(null)}>
                  Cancel
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      <div className="card space-y-4">
        <div>
          <h3 className="text-base font-semibold text-slate-900">Current shared addresses</h3>
          <p className="text-sm text-slate-500">Read-only preview for non-admins, editable for administrators.</p>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading shared addresses...</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-600">
                <tr>
                  <th className="px-3 py-2">Label</th>
                  <th className="px-3 py-2">Address</th>
                  <th className="px-3 py-2">City</th>
                  {isAdmin && <th className="px-3 py-2">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-b border-slate-100">
                    <td className="px-3 py-3">{item.label}</td>
                    <td className="px-3 py-3">{item.address_line1 ?? "—"}</td>
                    <td className="px-3 py-3">{item.city ?? "—"}</td>
                    {isAdmin && (
                      <td className="px-3 py-3">
                        <div className="flex gap-2">
                          <button className="btn-secondary" onClick={() => startEditing(item)}>
                            Edit
                          </button>
                          <button className="btn-secondary" onClick={() => void handleDelete(item)}>
                            Delete
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
