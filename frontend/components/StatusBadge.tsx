// Ported from the user's other project (components/enterprise/StatusBadge.tsx)
// and adapted to S2PNexus's lowercase status vocabulary (draft/submitted/
// approved/rejected, plus a few extra states other document types use).

const semantic: Record<string, { background: string; color: string }> = {
  APPROVED: { background: "#dcfce7", color: "#166534" },
  REJECTED: { background: "#ffe4e6", color: "#9f1239" },
  CANCELLED: { background: "#fee2e2", color: "#991b1b" },
  CLOSED: { background: "#dbeafe", color: "#1e40af" },
  SUBMITTED: { background: "#fef3c7", color: "#92400e" },
  PENDING_APPROVAL: { background: "#fef3c7", color: "#92400e" },
  IN_APPROVAL: { background: "#fef3c7", color: "#92400e" },
  PENDING: { background: "#fef3c7", color: "#92400e" },
  ORDERED: { background: "#e0e7ff", color: "#3730a3" },
  ACKNOWLEDGED: { background: "#e0e7ff", color: "#3730a3" },
  SCHEDULED: { background: "#ede9fe", color: "#5b21b6" },
  DRAFT: { background: "#f1f5f9", color: "#475569" },
};

const displayLabels: Record<string, string> = {
  SUBMITTED: "In Approval",
  PENDING_APPROVAL: "In Approval",
  IN_APPROVAL: "In Approval",
  PENDING: "In Approval",
};

export function StatusBadge({ status }: { status: string }) {
  const rawStatus = (status ?? "draft").toString().toUpperCase().replace(/-/g, "_");
  const label = displayLabels[rawStatus] ?? rawStatus.replace(/_/g, " ");
  const style = semantic[rawStatus] ?? { background: "#f1f5f9", color: "#475569" };
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-1 text-xs font-medium capitalize"
      style={{ background: style.background, color: style.color }}
    >
      {label.toLowerCase()}
    </span>
  );
}
