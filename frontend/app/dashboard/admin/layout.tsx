"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/dashboard/admin/core-p2p", label: "Core P2P" },
  { href: "/dashboard/admin/sourcing", label: "Sourcing & Contracts" },
  { href: "/dashboard/admin/suppliers", label: "Supplier Management" },
  { href: "/dashboard/admin/platform-data", label: "Platform & Data" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Admin</h1>
          <p className="mt-1 text-sm text-slate-500">
            A unified admin control plane for enterprise procurement, sourcing, supplier, and platform data.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => {
            const active = pathname === tab.href || pathname.startsWith(tab.href + "/");
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`rounded-md px-3 py-2 text-sm font-medium ${
                  active ? "bg-brand-600 text-white" : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
      </div>
      {children}
    </div>
  );
}
