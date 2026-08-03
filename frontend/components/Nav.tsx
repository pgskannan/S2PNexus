"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { extractErrorMessage, listWorkflowNotifications, markWorkflowNotificationRead } from "@/lib/api";
import type { Notification } from "@/lib/types";

const links = [
  { href: "/dashboard", label: "Overview", icon: "overview" },
  { href: "/dashboard/workflow", label: "My Approvals", icon: "workflow" },
  { href: "/dashboard/requisitions", label: "Requisitions", icon: "requisitions" },
  { href: "/dashboard/purchase-orders", label: "Purchase Orders", icon: "purchase-orders" },
  { href: "/dashboard/receipts", label: "Receipts", icon: "purchase-orders" },
  { href: "/dashboard/invoices", label: "Invoices", icon: "documents" },
  { href: "/dashboard/contracts", label: "Contracts", icon: "contracts" },
  { href: "/dashboard/documents", label: "Documents", icon: "documents" },
  { href: "/dashboard/sourcing", label: "Sourcing", icon: "sourcing" },
  { href: "/dashboard/spend", label: "Spend & Savings", icon: "spend-savings" },
  { href: "/dashboard/workflow/definitions", label: "Workflow rules", icon: "workflow" },
  { href: "/dashboard/admin/templates", label: "Templates", icon: "documents" },
  { href: "/dashboard/suppliers", label: "Suppliers", icon: "suppliers" },
  { href: "/dashboard/admin", label: "Admin", icon: "settings" },
  { href: "/dashboard/agent", label: "AI Agent", icon: "ai-agent" },
  { href: "/dashboard/agent-activity", label: "Agent Activity", icon: "agent-activity" },
];

// Vertical left sidebar nav -- replaces the old horizontal header, which no
// longer fit all 12 links on a single row at normal window widths. Sidebar is
// a fixed-width column; DashboardLayout offsets <main> to account for it.
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
    <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="" className="h-6 w-6" />
        <span className="text-lg font-semibold text-brand-700">S2P Nexus</span>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {links.map((link) => {
          const active =
            link.href === "/dashboard/workflow"
              ? pathname === "/dashboard/workflow" || pathname.startsWith("/dashboard/workflow/instances")
              : pathname === link.href ||
                (link.href !== "/dashboard" && pathname.startsWith(link.href));
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium ${
                active
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/icons/${link.icon}.svg`} alt="" className="h-4 w-4 shrink-0" />
              <span>{link.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-slate-200 px-3 py-4">
        {user && (
          <div className="relative">
            <button
              onClick={() => setShowNotifications((current) => !current)}
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-left text-sm font-medium text-slate-600"
            >
              Notifications {notifications.length > 0 ? `(${notifications.length})` : ""}
            </button>
            {showNotifications && (
              <div className="absolute bottom-full left-0 mb-2 w-80 rounded-lg border border-slate-200 bg-white p-3 shadow-lg">
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
                <ul className="max-h-64 space-y-2 overflow-y-auto">
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
          <p className="truncate text-sm text-slate-500">
            {user.full_name} &middot; {user.role.replace("_", " ")}
          </p>
        )}
        <button
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="btn-secondary w-full"
        >
          Log out
        </button>
      </div>
    </aside>
  );
}
