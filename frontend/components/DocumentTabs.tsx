"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { DocumentTabSignals } from "@/lib/documentTabs";

// SAP-Ariba-style document tab bar. Rendered on PR / PO detail pages; each tab
// appears only when the underlying document state allows it (see the tab
// visibility spec):
//
//   PR          always visible (parent PR for PO/invoice documents)
//   PO          only when the PR is fully approved AND a PO exists
//   Receipts    only when a PO exists AND a receipt exists (3-way)
//   Invoice     only when at least one invoice exists
//   IR          only when an invoice has been submitted (IR generated)
//   Payment     only when a payment run completed for an invoice
//   Approval Flow / History / Comments   always visible
export interface DocumentTabsProps {
  prId?: string | null;
  poId?: string | null;
  prApproved: boolean;
  signals: DocumentTabSignals;
}

export default function DocumentTabs({ prId, poId, prApproved, signals }: DocumentTabsProps) {
  const pathname = usePathname();

  const activeTab = pathname.startsWith("/dashboard/purchase-orders")
    ? "po"
    : pathname.startsWith("/dashboard/receipts")
    ? "receipts"
    : pathname.startsWith("/dashboard/invoices")
    ? "invoice"
    : "pr";

  const tabs: { key: string; label: string; href?: string; visible: boolean }[] = [
    { key: "pr", label: "PR", href: prId ? `/dashboard/requisitions/${prId}` : undefined, visible: !!prId },
    { key: "po", label: "PO", href: poId ? `/dashboard/purchase-orders/${poId}` : undefined, visible: !!poId && prApproved },
    { key: "receipts", label: "Receipts", href: poId ? `/dashboard/receipts?po=${poId}` : undefined, visible: !!poId && signals.hasReceipts },
    { key: "invoice", label: "Invoice", href: poId ? `/dashboard/invoices?po=${poId}` : undefined, visible: signals.hasInvoices },
    { key: "ir", label: "IR", href: poId ? `/dashboard/invoices?po=${poId}` : undefined, visible: signals.hasSubmittedInvoice },
    { key: "payment", label: "Payment", href: poId ? `/dashboard/invoices?po=${poId}` : undefined, visible: signals.hasPayment },
    { key: "approval", label: "Approval Flow", href: pathname, visible: true },
    { key: "history", label: "History", href: pathname, visible: true },
    { key: "comments", label: "Comments", href: pathname, visible: true },
  ];

  return (
    <nav className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
      {tabs
        .filter((tab) => tab.visible)
        .map((tab) => {
          const active = tab.key === activeTab;
          const className = `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
          }`;
          return tab.href ? (
            <Link key={tab.key} href={tab.href} className={className}>
              {tab.label}
            </Link>
          ) : (
            <span key={tab.key} title="Not available for this document" className={`${className} opacity-60`}>
              {tab.label}
            </span>
          );
        })}
    </nav>
  );
}
