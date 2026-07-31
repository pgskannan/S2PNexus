import { listGoodsReceipts, listInvoices } from "./api";

// Signals that drive the SAP-Ariba-style document tab visibility rules
// (docs/... tab-visibility spec). Each page computes these from the real
// documents it can see, then renders <DocumentTabs/>.
export interface DocumentTabSignals {
  /** At least one goods receipt exists for the PO. */
  hasReceipts: boolean;
  /** At least one invoice exists for the PO (or a non-PO invoice for the PR). */
  hasInvoices: boolean;
  /** An invoice has been submitted (beyond draft) -> IR exists. */
  hasSubmittedInvoice: boolean;
  /** A payment run has been completed for an invoice. */
  hasPayment: boolean;
}

/** PR lifecycles that count as "fully approved" for tab visibility. */
export const PR_APPROVED_LIFECYCLES = new Set(["approved", "po_created", "closed"]);

/** Invoice statuses that still count as draft (IR / invoice tab suppressed). */
const INVOICE_DRAFT_STATUSES = new Set(["pending", "draft"]);

export async function fetchDocumentTabSignals(poId?: string | null): Promise<DocumentTabSignals> {
  if (!poId) {
    return { hasReceipts: false, hasInvoices: false, hasSubmittedInvoice: false, hasPayment: false };
  }
  const [receipts, invoices] = await Promise.all([listGoodsReceipts(), listInvoices()]);
  const poReceipts = receipts.items.filter((r) => r.purchase_order_id === poId);
  const poInvoices = invoices.items.filter((i) => i.purchase_order_id === poId);
  // IR exists once any invoice for this PO has left draft (submitted / matched /
  // approved / rejected) -- the system (or a manual run) generates an IR at that
  // point. match_status "pending" also still means nothing has been processed.
  const hasSubmittedInvoice = poInvoices.some(
    (inv) =>
      !INVOICE_DRAFT_STATUSES.has(inv.status) ||
      (inv.match_status && inv.match_status !== "pending")
  );
  return {
    hasReceipts: poReceipts.length > 0,
    hasInvoices: poInvoices.length > 0,
    hasSubmittedInvoice,
    // Payment module is not wired to the frontend yet; keep the signal so the
    // tab appears automatically once a payment reference exists.
    hasPayment: false,
  };
}
