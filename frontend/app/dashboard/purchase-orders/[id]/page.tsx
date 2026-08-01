"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getPurchaseOrder,
  getPurchaseOrderVersions,
  listPurchaseOrderComments,
  addPurchaseOrderComment,
  listUserDirectory,
  transitionPurchaseOrderLifecycle,
  acknowledgePurchaseOrder,
  createGoodsReceipt,
  getSupplier,
  extractErrorMessage,
  type GoodsReceiptLineItemCreate,
} from "@/lib/api";
import type { PurchaseOrder } from "@/lib/types";
import AccountingSplitEditor from "@/components/AccountingSplitEditor";
import DocumentTabs from "@/components/DocumentTabs";
import CommentsPanel from "@/components/CommentsPanel";
import ActionRecommendationStrip from "@/components/ActionRecommendationStrip";
import {
  fetchDocumentTabSignals,
  type DocumentTabSignals,
} from "@/lib/documentTabs";

// PO lifecycle states where goods can still be received against this PO.
const RECEIVABLE_STATUSES = new Set(["ordered", "sent_to_supplier", "acknowledged", "partially_received"]);

const nextLifecycleSteps: Record<string, { value: string; label: string }[]> = {
  draft: [{ value: "pending_approval", label: "Submit for approval" }],
  pending_approval: [
    { value: "approved", label: "Approve" },
    { value: "cancelled", label: "Cancel" },
  ],
  approved: [
    { value: "ordered", label: "Mark ordered" },
    { value: "sent_to_supplier", label: "Send to supplier" },
    { value: "cancelled", label: "Cancel" },
  ],
  ordered: [
    { value: "sent_to_supplier", label: "Send to supplier" },
    { value: "cancelled", label: "Cancel" },
  ],
  sent_to_supplier: [{ value: "cancelled", label: "Cancel" }],
  acknowledged: [
    { value: "partially_received", label: "Mark partially received" },
    { value: "fully_received", label: "Mark fully received" },
    { value: "cancelled", label: "Cancel" },
  ],
  partially_received: [
    { value: "fully_received", label: "Mark fully received" },
    { value: "cancelled", label: "Cancel" },
  ],
  fully_received: [{ value: "invoiced", label: "Mark invoiced" }],
  invoiced: [{ value: "closed", label: "Close" }],
};

export default function PurchaseOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [supplierName, setSupplierName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastBudgetWarnings, setLastBudgetWarnings] = useState<PurchaseOrder["budget_warnings"]>(null);
  const [prId, setPrId] = useState<string | null>(null);
  const [docSignals, setDocSignals] = useState<DocumentTabSignals>({
    hasReceipts: false,
    hasInvoices: false,
    hasSubmittedInvoice: false,
    hasPayment: false,
  });
  const [poVersions, setPoVersions] = useState<import("@/lib/types").PurchaseOrderVersion[]>([]);
  const [actorNames, setActorNames] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<import("@/lib/types").ProcurementComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [secondaryTab, setSecondaryTab] = useState<"history" | "comments">("history");
  const [showReceiveForm, setShowReceiveForm] = useState(false);
  const [receiveQty, setReceiveQty] = useState<Record<string, string>>({});
  const [receiveBusy, setReceiveBusy] = useState(false);
  const [receiveError, setReceiveError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await getPurchaseOrder(params.id);
      setPo(data);
      if (data.supplier_id) {
        try {
          const supplier = await getSupplier(data.supplier_id);
          setSupplierName(supplier.name);
        } catch {
          setSupplierName(null);
        }
      }
      // Ariba-style tab visibility: derive the PR approval state plus
      // receipt/invoice existence from the real documents.
      setPrId(data.requisition_id ?? null);
      setDocSignals(await fetchDocumentTabSignals(data.id));
      // History / Comments panels for the PO: version history + comment
      // thread. (No Approval Flow tab here -- the PO doesn't run its own
      // separate approval workflow visualization; that lives on the PR.)
      const [versions, directory] = await Promise.all([
        getPurchaseOrderVersions(data.id),
        listUserDirectory({ limit: 1000 }).catch(() => null),
      ]);
      setPoVersions(versions);
      setActorNames(
        directory
          ? Object.fromEntries(directory.items.map((user) => [user.id, user.full_name || user.email]))
          : {}
      );
      try {
        setComments(await listPurchaseOrderComments(data.id));
        setCommentsError(null);
      } catch (err2) {
        setCommentsError(extractErrorMessage(err2));
      } finally {
        setCommentsLoading(false);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  async function handleTransition(lifecycleStatus: string) {
    setBusy(true);
    setError(null);
    try {
      const updated = await transitionPurchaseOrderLifecycle(params.id, lifecycleStatus);
      setPo(updated);
      setLastBudgetWarnings(updated.budget_warnings ?? null);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAcknowledge() {
    setBusy(true);
    setError(null);
    try {
      const updated = await acknowledgePurchaseOrder(params.id);
      setPo(updated);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAddComment(text: string) {
    const added = await addPurchaseOrderComment(params.id, text);
    setComments((current) => [added, ...current]);
  }

  function openReceiveForm() {
    if (po) {
      setReceiveQty(Object.fromEntries(po.line_items.map((li) => [li.id, li.quantity])));
    }
    setReceiveError(null);
    setShowReceiveForm(true);
  }

  async function handleSubmitReceipt() {
    if (!po) return;
    const lineItems: GoodsReceiptLineItemCreate[] = po.line_items
      .map((li) => ({
        purchase_order_line_item_id: li.id,
        quantity_received: receiveQty[li.id] ?? "0",
        condition_status: "good",
      }))
      .filter((li) => Number(li.quantity_received) > 0);

    if (lineItems.length === 0) {
      setReceiveError("Enter a quantity received for at least one line item.");
      return;
    }

    setReceiveBusy(true);
    setReceiveError(null);
    try {
      // status: "received" records the goods directly rather than routing
      // through the draft/submit/approve/post receipt workflow -- this is a
      // quick-receive entry point, matching how the auto-receipt service
      // records system-generated receipts elsewhere in the app.
      await createGoodsReceipt(po.id, {
        status: "received",
        inspection_status: "passed",
        notes: "Recorded from PO detail page.",
        line_items: lineItems,
      });
      setShowReceiveForm(false);
      await load();
    } catch (err) {
      setReceiveError(extractErrorMessage(err));
    } finally {
      setReceiveBusy(false);
    }
  }

  if (error && !po) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!po) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  const actions = nextLifecycleSteps[po.lifecycle_status] ?? [];
  const canAcknowledge = po.lifecycle_status === "sent_to_supplier" && po.acknowledgment_status !== "acknowledged";
  const canReceive = RECEIVABLE_STATUSES.has(po.lifecycle_status);

  const headerActionBar = (
    <>
      {canAcknowledge && (
        <button disabled={busy} onClick={handleAcknowledge} className="btn-secondary">
          Acknowledge
        </button>
      )}
      {actions.map((action) => (
        <button
          key={action.value}
          disabled={busy}
          onClick={() => handleTransition(action.value)}
          className="btn-primary"
        >
          {action.label}
        </button>
      ))}
    </>
  );

  const poRecommendation = (() => {
    if (lastBudgetWarnings && lastBudgetWarnings.length > 0) {
      return "Approved with budget warnings -- see details below before proceeding.";
    }
    switch (po.lifecycle_status) {
      case "draft":
        return "This PO is still a draft. Submit it for approval when it's ready.";
      case "pending_approval":
        return "Awaiting approval before it can be sent to the supplier.";
      case "approved":
        return "Approved -- mark it ordered or send it to the supplier to continue.";
      case "ordered":
        return "Ordered. Receive goods as they arrive, or send to the supplier if that hasn't happened yet.";
      case "sent_to_supplier":
        return canAcknowledge
          ? "Sent to supplier -- awaiting acknowledgment."
          : "Sent to supplier -- receive goods as they arrive.";
      case "acknowledged":
        return "Acknowledged by the supplier -- receive goods as they arrive.";
      case "partially_received":
        return "Partially received -- receive the remaining quantity or mark it fully received.";
      case "fully_received":
        return "Fully received -- ready to invoice.";
      case "invoiced":
        return "Invoiced -- awaiting closure.";
      case "closed":
        return "Closed -- no further action needed.";
      case "cancelled":
        return "This PO was cancelled.";
      default:
        return "No action items right now.";
    }
  })();

  const poStripActions = [
    ...(canAcknowledge
      ? [{ label: "Acknowledge PO", tone: "warning" as const, onClick: handleAcknowledge }]
      : []),
    ...(canReceive
      ? [{ label: "Receive goods", tone: "critical" as const, onClick: openReceiveForm }]
      : []),
    ...(lastBudgetWarnings && lastBudgetWarnings.length > 0
      ? [{ label: "Budget warnings", count: lastBudgetWarnings.length, tone: "critical" as const, onClick: () => setSecondaryTab("history") }]
      : []),
    { label: "History", count: poVersions.length, onClick: () => setSecondaryTab("history") },
    { label: "Comments", count: comments.length, onClick: () => setSecondaryTab("comments") },
  ];

  return (
    <div className="max-w-4xl space-y-6">
      <DocumentTabs prId={prId} poId={po.id} signals={docSignals} />
      <button
        onClick={() => router.push("/dashboard/purchase-orders")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to purchase orders
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-mono text-xs text-slate-400">{po.order_number}</p>
            <h1 className="text-xl font-semibold">
              {supplierName ?? "Purchase order"}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Version {po.version_number}
              {po.amendment_status !== "original" ? ` · ${po.amendment_status}` : ""}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span className="badge bg-slate-100 text-slate-700 capitalize">
              {po.lifecycle_status}
            </span>
            {(canAcknowledge || actions.length > 0) && (
              <div className="flex flex-wrap justify-end gap-2">{headerActionBar}</div>
            )}
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Subtotal</dt>
            <dd>{po.currency} {po.subtotal ?? "0.00"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Shipping</dt>
            <dd>
              {po.currency} {po.shipping_amount ?? "0.00"}{" "}
              <span className="text-xs text-slate-400">({po.shipping_allocation_method})</span>
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Tax</dt>
            <dd>{po.currency} {po.tax_total ?? "0.00"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Grand total</dt>
            <dd className="font-semibold">{po.currency} {po.grand_total ?? po.total_amount ?? "0.00"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Incoterms</dt>
            <dd>{po.incoterms ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Payment terms</dt>
            <dd>{po.payment_terms ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Acknowledgment</dt>
            <dd className="capitalize">{po.acknowledgment_status}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Created</dt>
            <dd>{new Date(po.created_at).toLocaleString()}</dd>
          </div>
        </dl>

        <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 text-sm">
          <div>
            <dt className="text-slate-500">Ship to</dt>
            <dd>
              {po.ship_to_name ? (
                <>
                  {po.ship_to_name}
                  {po.ship_to_address_line1 ? `, ${po.ship_to_address_line1}` : ""}
                  {po.ship_to_city ? `, ${po.ship_to_city}` : ""}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Bill to</dt>
            <dd>
              {po.bill_to_name ? (
                <>
                  {po.bill_to_name}
                  {po.bill_to_address_line1 ? `, ${po.bill_to_address_line1}` : ""}
                  {po.bill_to_city ? `, ${po.bill_to_city}` : ""}
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </div>

        {po.notes && (
          <p className="border-t border-slate-100 pt-4 text-sm text-slate-500">{po.notes}</p>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      <ActionRecommendationStrip
        title="PO actions"
        description="Track this purchase order's progress toward receiving and invoicing."
        recommendation={poRecommendation}
        actions={poStripActions}
      />

      {lastBudgetWarnings && lastBudgetWarnings.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <p className="font-medium">Approved with budget warnings:</p>
          <ul className="mt-1 list-disc pl-5">
            {lastBudgetWarnings.map((w, i) => (
              <li key={i}>
                {w.scope_level} {w.scope_code}: requested {w.requested_amount}, available {w.available}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showReceiveForm && (
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Receive goods</h2>
            <button className="text-sm text-slate-400 hover:text-slate-600" onClick={() => setShowReceiveForm(false)}>
              Cancel
            </button>
          </div>
          <p className="text-sm text-slate-500">
            Enter the quantity received for each line item. Leave a line at 0 to skip it.
          </p>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Ordered qty</th>
                  <th className="py-2 pr-4">Qty received</th>
                </tr>
              </thead>
              <tbody>
                {po.line_items.map((li) => (
                  <tr key={li.id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2 pr-4">{li.line_number}</td>
                    <td className="py-2 pr-4">{li.description}</td>
                    <td className="py-2 pr-4">{li.quantity}</td>
                    <td className="py-2 pr-4">
                      <input
                        type="number"
                        min="0"
                        step="any"
                        className="input-field w-28"
                        value={receiveQty[li.id] ?? ""}
                        onChange={(e) => setReceiveQty((cur) => ({ ...cur, [li.id]: e.target.value }))}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {receiveError && <p className="text-sm text-red-600">{receiveError}</p>}
          <button disabled={receiveBusy} onClick={handleSubmitReceipt} className="btn-primary">
            {receiveBusy ? "Recording..." : "Record receipt"}
          </button>
        </div>
      )}

      <div className="card space-y-3">
        <h2 className="text-lg font-semibold">Line items</h2>
        {po.line_items.length === 0 && (
          <p className="text-sm text-slate-400">No line items on this purchase order.</p>
        )}
        {po.line_items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Description</th>
                  <th className="py-2 pr-4">Qty</th>
                  <th className="py-2 pr-4">Unit price</th>
                  <th className="py-2 pr-4">Line total</th>
                  <th className="py-2 pr-4">Shipping alloc.</th>
                  <th className="py-2 pr-4">Account code</th>
                  <th className="py-2 pr-4">Accounting split</th>
                </tr>
              </thead>
              <tbody>
                {po.line_items.map((li) => (
                  <tr key={li.id} className="border-b border-slate-50 last:border-0 align-top">
                    <td className="py-2 pr-4">{li.line_number}</td>
                    <td className="py-2 pr-4">{li.description}</td>
                    <td className="py-2 pr-4">{li.quantity}</td>
                    <td className="py-2 pr-4">{li.unit_price ?? "—"}</td>
                    <td className="py-2 pr-4">{li.line_total ?? "—"}</td>
                    <td className="py-2 pr-4">{li.allocated_shipping_amount ?? "—"}</td>
                    <td className="py-2 pr-4">
                      {li.account_code ?? "—"}
                      {li.account_code_is_override && (
                        <span className="ml-1 text-xs text-slate-400">(override)</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <AccountingSplitEditor
                        purchaseOrderId={po.id}
                        lineItemId={li.id}
                        lineTotal={li.line_total}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card space-y-4 p-0 overflow-hidden">
        <div className="flex gap-1 border-b border-slate-100 bg-slate-50 px-3 pt-2">
          {([
            { key: "history", label: `History${poVersions.length ? ` (${poVersions.length})` : ""}` },
            { key: "comments", label: `Comments${comments.length ? ` (${comments.length})` : ""}` },
          ] as const).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSecondaryTab(tab.key)}
              className={`rounded-t-md px-3 py-2 text-sm font-medium transition ${
                secondaryTab === tab.key
                  ? "bg-white text-brand-700 border border-b-0 border-slate-100"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {secondaryTab === "history" &&
            (poVersions.length === 0 ? (
              <p className="text-sm text-slate-400">No version history yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {poVersions.map((v) => (
                  <li key={v.id} className="py-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium text-slate-700">
                        V{v.version_number} ·{" "}
                        <span className="capitalize">{v.change_type.replace(/_/g, " ")}</span>
                      </span>
                      <time className="text-xs text-slate-400">{new Date(v.created_at).toLocaleString()}</time>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">By {actorNames[v.created_by] || "System"}</p>
                    {v.changes && Object.keys(v.changes).length > 0 && (
                      <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-600">
                        {JSON.stringify(v.changes, null, 2)}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            ))}

          {secondaryTab === "comments" && (
            <CommentsPanel
              items={comments}
              loading={commentsLoading}
              error={commentsError}
              authorNames={actorNames}
              onAdd={handleAddComment}
              bare
            />
          )}
        </div>
      </div>
    </div>
  );
}
