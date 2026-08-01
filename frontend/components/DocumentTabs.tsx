"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { DocumentTabSignals } from "@/lib/documentTabs";

// Document navigation bar shared by the PR/PO detail pages and the Receipts /
// Invoices list pages. PR / PO / Receipts / Invoice are ALWAYS shown so you can
// move between the source-to-pay document family from anywhere (clicking a tab
// from a document lands on a page that still has the tab bar, so you never get
// stranded). IR and Payment appear only once their document state exists.
//
// Approval Flow / History / Comments are NOT tabs -- they render inline inside
// the PR/PO detail pages so that content stays visible on the document.
export interface DocumentTabsProps {
  prId?: string | null;
  poId?: string | null;
  signals?: DocumentTabSignals;
}

export default function DocumentTabs({ prId, poId, signals }: DocumentTabsProps) {
  const pathname = usePathname();

  const activeTab = pathname.startsWith("/dashboard/purchase-orders")
    ? "po"
    : pathname.startsWith("/dashboard/receipts")
    ? "receipts"
    : pathname.startsWith("/dashboard/invoices")
    ? "invoice"
    : "pr";

  const poQuery = poId ? `?po=${poId}` : "";

  const tabs: { key: string; label: string; href: string; visible: boolean }[] = [
    { key: "pr", label: "PR", href: prId ? `/dashboard/requisitions/${prId}` : "/dashboard/requisitions", visible: true },
    { key: "po", label: "PO", href: poId ? `/dashboard/purchase-orders/${poId}` : "/dashboard/purchase-orders", visible: true },
    { key: "receipts", label: "Receipts", href: `/dashboard/receipts${poQuery}`, visible: true },
    { key: "invoice", label: "Invoice", href: `/dashboard/invoices${poQuery}`, visible: true },
    { key: "ir", label: "IR", href: `/dashboard/invoices${poQuery}`, visible: !!signals?.hasSubmittedInvoice },
    { key: "payment", label: "Payment", href: `/dashboard/invoices${poQuery}`, visible: !!signals?.hasPayment },
  ];

  return (
    <nav className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
      {tabs
        .filter((tab) => tab.visible)
        .map((tab) => {
          const active = tab.key === activeTab;
          return (
            <Link
              key={tab.key}
              href={tab.href}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
    </nav>
  );
}

