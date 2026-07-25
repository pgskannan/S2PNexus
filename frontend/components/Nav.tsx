"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";

const links = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/requisitions", label: "Requisitions" },
  { href: "/dashboard/contracts", label: "Contracts" },
  { href: "/dashboard/sourcing", label: "Sourcing" },
  { href: "/dashboard/spend", label: "Spend & Savings" },
  { href: "/dashboard/suppliers", label: "Suppliers" },
  { href: "/dashboard/agent", label: "AI Agent" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();

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
