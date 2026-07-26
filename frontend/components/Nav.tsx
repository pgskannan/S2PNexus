"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { extractErrorMessage, listWorkflowNotifications, markWorkflowNotificationRead } from "@/lib/api";
import type { Notification } from "@/lib/types";

const links = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/requisitions", label: "Requisitions" },
  { href: "/dashboard/contracts", label: "Contracts" },
  { href: "/dashboard/sourcing", label: "Sourcing" },
  { href: "/dashboard/spend", label: "Spend & Savings" },
  { href: "/dashboard/workflow", label: "Workflow" },
  { href: "/dashboard/suppliers", label: "Suppliers" },
  { href: "/dashboard/settings", label: "Settings" },
  { href: "/dashboard/agent", label: "AI Agent" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [loadingNotifications, setLoadingNotifications] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadNotifications() {
    if (!user) return;
    setLoadingNotifications(true);
    setError(null);
    try {
      const res = await listWorkflowNotifications({ unread_only: true, limit: 10 });
      setNotifications(res.items);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoadingNotifications(false);
    }
  }

  useEffect(() => {
    if (user) {
      loadNotifications();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  async function handleMarkRead(id: string) {
    try {
      await markWorkflowNotificationRead(id);
      setNotifications((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-8">
          <span className="text-lg font-semibold text-brand-700">
            S2PNexus
          </span>
          <nav className="flex gap-1">
            {links.map((link) => {
              const active =
                pathname === link.href ||
                (link.href !== "/dashboard" && pathname.startsWith(link.href));
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-md px-3 py-2 text-sm font-medium ${
                    active
                      ? "bg-brand-50 text-brand-700"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          {user && (
            <div className="relative">
              <button
                onClick={() => setShowNotifications((current) => !current)}
                className="rounded-md border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600"
              >
                Notifications {notifications.length > 0 ? `(${notifications.length})` : ""}
              </button>
              {showNotifications && (
                <div className="absolute right-0 mt-2 w-80 rounded-lg border border-slate-200 bg-white p-3 shadow-lg">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-semibold">Unread notifications</span>
                    <button onClick={() => setShowNotifications(false)} className="text-xs text-slate-400">
                      Close
                    </button>
                  </div>
                  {error && <p className="mb-2 text-xs text-red-600">{error}</p>}
                  {loadingNotifications && <p className="text-sm text-slate-400">Loading...</p>}
                  {!loadingNotifications && notifications.length === 0 && (
                    <p className="text-sm text-slate-400">No unread notifications.</p>
                  )}
                  <ul className="space-y-2">
                    {notifications.map((item) => (
                      <li key={item.id} className="rounded border border-slate-100 p-2 text-sm">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="font-medium">{item.title}</p>
                            <p className="mt-1 text-xs text-slate-500">{item.message}</p>
                          </div>
                          <button onClick={() => handleMarkRead(item.id)} className="text-xs text-brand-600">
                            Mark read
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          {user && (
            <span className="text-sm text-slate-500">
              {user.full_name} &middot; {user.role.replace("_", " ")}
            </span>
          )}
          <button
            onClick={() => {
              logout();
              router.replace("/login");
            }}
            className="btn-secondary"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
