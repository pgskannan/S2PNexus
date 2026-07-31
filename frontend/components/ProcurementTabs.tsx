"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Horizontal tab bar for the procurement workspace: PR -> PO -> Receipts ->
// Invoices. Rendered at the top of each of those pages so you can jump between
// the source-to-pay stages without hunting through the sidebar.
const tabs = [
  { href: "/dashboard/requisitions", label: "PR · Requisitions" },
  { href: "/dashboard/purchase-orders", label: "PO · Purchase Orders" },
  { href: "/dashboard/receipts", label: "Receipts" },
  { href: "/dashboard/invoices", label: "Invoice" },
];

export default function ProcurementTabs() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
      {tabs.map((tab) => {
        const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              active
                ? "bg-brand-600 text-white"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
