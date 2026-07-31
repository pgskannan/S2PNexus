"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { DocumentTabSignals } from "@/lib/documentTabs";

// The in-document tab bar (SAP-Ariba style) shared by the PR and PO detail
// pages. Document tabs (PR / PO / Receipts / Invoice / IR / Payment) navigate
// to the corresponding document, appearing only when the visibility rules in
// the tab-visibility spec allow them. Section tabs (Approval Flow / History /
// Comments) are ALWAYS visible and switch the *host page's* own local section
// state (they are not links) -- the host page renders the matching panel.
export type DocumentSectionKey = "approval" | "history" | "comments";

export interface DocumentTabsProps {
  prId?: string | null;
  poId?: string | null;
  prApproved: boolean;
  signals: DocumentTabSignals;
  activeSection?: DocumentSectionKey | null;
  onSectionChange?: (section: DocumentSectionKey) => void;
}

export default function DocumentTabs({
  prId,
  poId,
  prApproved,
  signals,
  activeSection,
  onSectionChange,
}: DocumentTabsProps) {
  const pathname = usePathname();

  const activeDocTab = pathname.startsWith("/dashboard/purchase-orders")
    ? "po"
    : pathname.startsWith("/dashboard/receipts")
    ? "receipts"
    : pathname.startsWith("/dashboard/invoices")
    ? "invoice"
    : "pr";

  const docTabs: { key: string; label: string; href?: string; visible: boolean }[] = [
    { key: "pr", label: "PR", href: prId ? `/dashboard/requisitions/${prId}` : undefined, visible: !!prId },
    { key: "po", label: "PO", href: poId ? `/dashboard/purchase-orders/${poId}` : undefined, visible: !!poId && prApproved },
    { key: "receipts", label: "Receipts", href: poId ? `/dashboard/receipts?po=${poId}` : undefined, visible: !!poId && signals.hasReceipts },
    { key: "invoice", label: "Invoice", href: poId ? `/dashboard/invoices?po=${poId}` : undefined, visible: signals.hasInvoices },
    { key: "ir", label: "IR", href: poId ? `/dashboard/invoices?po=${poId}` : undefined, visible: signals.hasSubmittedInvoice },
    { key: "payment", label: "Payment", href: poId ? `/dashboard/invoices?po=${poId}` : undefined, visible: signals.hasPayment },
  ];

  const sections: { key: DocumentSectionKey; label: string }[] = [
    { key: "approval", label: "Approval Flow" },
    { key: "history", label: "History" },
    { key: "comments", label: "Comments" },
  ];

  return (
    <nav className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
      {docTabs
        .filter((tab) => tab.visible)
        .map((tab) => {
          const active = tab.key === activeDocTab;
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
      <span className="mx-1 h-4 w-px bg-slate-200" aria-hidden />
      {sections.map((section) => {
        const active = activeSection === section.key;
        const className = `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
        }`;
        return onSectionChange ? (
          <button
            key={section.key}
            type="button"
            onClick={() => onSectionChange(section.key)}
            className={className}
          >
            {section.label}
          </button>
        ) : (
          <span key={section.key} className={`${className} opacity-60`}>
            {section.label}
          </span>
        );
      })}
    </nav>
  );
}

