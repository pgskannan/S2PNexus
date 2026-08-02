"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import {
  deleteUser,
  extractErrorMessage,
  getMe,
  listUserDirectory,
  listUsers,
  startActAsSession,
  updateUser,
} from "@/lib/api";
import type { User, UserRole, UserUpdate } from "@/lib/types";

const USER_ROLE_OPTIONS: UserRole[] = [
  "administrator",
  "procurement_manager",
  "buyer",
  "requester",
  "supplier_manager",
  "category_manager",
  "ap_clerk",
  "contract_manager",
];

const ROLE_LABELS: Record<UserRole, string> = {
  administrator: "Administrator",
  procurement_manager: "Procurement Manager",
  buyer: "Buyer",
  requester: "Requester",
  supplier_manager: "Supplier Manager",
  category_manager: "Category Manager",
  ap_clerk: "AP Clerk",
  contract_manager: "Contract Manager",
};

export default function UsersAdminPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const originalSession = useAuthStore((state) => state.originalSession);
  const startActAs = useAuthStore((state) => state.startActAs);
  const setUser = useAuthStore((state) => state.setUser);
  const setActAs = useAuthStore((state) => state.setActAs);
  const isAdmin = user?.role === "administrator";
  // Already impersonating someone -- the entry point is only for the admin's
  // own (original) session, so it's hidden rather than allowing act-as
  // chaining. Exiting the current session (via the banner) brings it back.
  const isImpersonating = Boolean(originalSession);
  const [actingAsUserId, setActingAsUserId] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [skip, setSkip] = useState(0);
  const [limit] = useState(10);
  const [total, setTotal] = useState(0);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formState, setFormState] = useState<UserUpdate>({});

  const selectedUser = useMemo(() => users.find((item) => item.id === selectedUserId) ?? null, [selectedUserId, users]);

  async function loadUsers() {
    setLoading(true);
    setError(null);
    try {
      if (!isAdmin) {
        const data = await listUserDirectory({ limit: 1000 });
        setUsers(
          data.items.map((item) => ({
            ...item,
            role: "requester",
            is_active: true,
            is_superuser: false,
          }))
        );
        setTotal(data.items.length);
        return;
      }
      const data = await listUsers({ skip, limit, search, sort_by: "email", sort_order: "asc" });
      setUsers(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadUsers();
  }, [skip, isAdmin]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSkip(0);
      void loadUsers();
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [search]);

  function startEditing(userItem: User) {
    setSelectedUserId(userItem.id);
    setFormState({
      role: userItem.role,
      is_active: userItem.is_active,
      is_superuser: userItem.is_superuser,
    });
  }

  async function handleSave() {
    if (!selectedUser) return;
    setSaving(true);
    setError(null);
    try {
      await updateUser(selectedUser.id, formState);
      setSelectedUserId(null);
      await loadUsers();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(userItem: User) {
    if (!window.confirm(`Delete ${userItem.email}?`)) return;
    setError(null);
    try {
      await deleteUser(userItem.id);
      setSelectedUserId(null);
      await loadUsers();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  async function handleActAs(userItem: User) {
    if (!window.confirm(`Act as ${userItem.full_name} (${userItem.email})? You'll see the app exactly as they do.`)) {
      return;
    }
    setActingAsUserId(userItem.id);
    setError(null);
    try {
      const session = await startActAsSession(userItem.id);
      startActAs(session);
      // startActAs() clears `user` so AuthGuard would normally re-fetch it,
      // but fetch it here too so the redirect below lands with the banner
      // already showing the target's name instead of a flash of "...".
      const profile = await getMe(session.access_token);
      setUser(profile);
      setActAs(profile.act_as ?? null);
      router.replace("/dashboard");
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setActingAsUserId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">User & Access Management</h2>
        <p className="mt-1 text-sm text-slate-500">
          Review user accounts, adjust roles, and manage active/superuser state across the tenant.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">User directory</h3>
            <p className="text-sm text-slate-500">Showing {Math.min(limit, users.length)} of {total} users.</p>
          </div>
          <div className="flex gap-2">
            <input
              className="input-field min-w-[220px]"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search email or name"
            />
            <button className="btn-secondary" onClick={() => void loadUsers()}>
              Refresh
            </button>
          </div>
        </div>

        {!isAdmin && (
          <p className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
            You can view the current user list, but only administrators can edit or remove users.
          </p>
        )}

        {loading ? (
          <p className="text-sm text-slate-500">Loading users...</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-slate-600">
                <tr>
                  <th className="px-3 py-2">Email</th>
                  <th className="px-3 py-2">Name</th>
                  {isAdmin && <th className="px-3 py-2">Role</th>}
                  {isAdmin && <th className="px-3 py-2">Active</th>}
                  {isAdmin && <th className="px-3 py-2">Superuser</th>}
                  {isAdmin && <th className="px-3 py-2">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {users.map((item) => (
                  <tr key={item.id} className="border-b border-slate-100">
                    <td className="px-3 py-3">{item.email}</td>
                    <td className="px-3 py-3">{item.full_name}</td>
                    {isAdmin && <td className="px-3 py-3">{ROLE_LABELS[item.role]}</td>}
                    {isAdmin && <td className="px-3 py-3">{item.is_active ? "Yes" : "No"}</td>}
                    {isAdmin && <td className="px-3 py-3">{item.is_superuser ? "Yes" : "No"}</td>}
                    {isAdmin && (
                      <td className="px-3 py-3">
                        <div className="flex gap-2">
                          <button className="btn-secondary" onClick={() => startEditing(item)}>
                            Edit
                          </button>
                          <button className="btn-secondary" onClick={() => void handleDelete(item)}>
                            Delete
                          </button>
                          {!isImpersonating && item.role !== "administrator" && !item.is_superuser && item.id !== user?.id && (
                            <button
                              className="btn-secondary"
                              disabled={actingAsUserId === item.id}
                              onClick={() => void handleActAs(item)}
                              title="View the app as this user"
                            >
                              {actingAsUserId === item.id ? "Starting..." : "Act as"}
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <button className="btn-secondary" disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - limit))}>
            Previous
          </button>
          <span className="text-sm text-slate-500">Page {skip / limit + 1}</span>
          <button className="btn-secondary" disabled={skip + limit >= total} onClick={() => setSkip(skip + limit)}>
            Next
          </button>
        </div>
      </div>

      {isAdmin && selectedUser && (
        <div className="card space-y-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Edit {selectedUser.email}</h3>
            <p className="text-sm text-slate-500">Update the role and access flags for this user.</p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label">Role</label>
              <select
                className="input-field"
                value={formState.role ?? selectedUser.role}
                onChange={(event) => setFormState({ ...formState, role: event.target.value as UserRole })}
              >
                {USER_ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-3 rounded border border-slate-200 bg-slate-50 px-3 py-3">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={formState.is_active ?? selectedUser.is_active}
                  onChange={(event) => setFormState({ ...formState, is_active: event.target.checked })}
                />
                Active
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={formState.is_superuser ?? selectedUser.is_superuser}
                  onChange={(event) => setFormState({ ...formState, is_superuser: event.target.checked })}
                />
                Superuser
              </label>
            </div>
          </div>

          <div className="flex gap-3">
            <button className="btn-primary" onClick={() => void handleSave()} disabled={saving}>
              {saving ? "Saving..." : "Save changes"}
            </button>
            <button className="btn-secondary" onClick={() => setSelectedUserId(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
