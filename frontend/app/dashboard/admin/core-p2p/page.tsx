import AdminActivityCard from "@/components/AdminActivityCard";

const cards = [
  {
    title: "User & Access Management",
    description: "List and manage enterprise users, roles, active status, and superuser access.",
    status: "Live" as const,
    href: "/dashboard/admin/users",
  },
  {
    title: "Custom group assignments",
    description: "Create and assign custom approval or procurement groups across the organization.",
    status: "Coming soon" as const,
  },
  {
    title: "Dynamic approval matrix",
    description: "Who approves what: roles, amount limits, category scope, backups, delegation windows, and SLA targets.",
    status: "Live" as const,
    href: "/dashboard/admin/approvals",
  },
  {
    title: "Delegated approvals",
    description: "Backup approvers and delegation windows are managed per role in the dynamic approval matrix.",
    status: "Live" as const,
    href: "/dashboard/admin/approvals",
  },
  {
    title: "Active approval queues",
    description: "Review the current workflow task queues and pending approvals.",
    status: "Live" as const,
    href: "/dashboard/workflow/instances",
  },
  {
    title: "Catalog Management",
    description: "Manage supplier product catalogs, item listings, and procurement catalog mappings.",
    status: "Coming soon" as const,
  },
  {
    title: "Approval routing lookup tables",
    description: "View and maintain approval routing lookup tables used by workflow definitions.",
    status: "Live" as const,
    href: "/dashboard/workflow/definitions",
  },
  {
    title: "Custom enumerations",
    description: "Define custom dropdowns, tags, and procurement enumerations for enterprise workflows.",
    status: "Coming soon" as const,
  },
  {
    title: "Tax calculation matrices",
    description: "Configure tax rate and tax code matrices for procurement transactions.",
    status: "Coming soon" as const,
  },
  {
    title: "Budget rules",
    description: "Create and review budget rules that gate spend and purchase approvals.",
    status: "Live" as const,
    href: "/dashboard/admin/budgets",
  },
  {
    title: "Email templates",
    description: "Configure lifecycle email content (subject, body, footer, branding) for PR, PO, receipts, invoices, and more.",
    status: "Live" as const,
    href: "/dashboard/admin/email-templates",
  },
  {
    title: "P-Card controls",
    description: "Manage procurement card usage rules and spend limits across the enterprise.",
    status: "Coming soon" as const,
  },
  {
    title: "Site configuration / feature flags",
    description: "Control platform-wide feature flags, tenant settings, and site configuration.",
    status: "Coming soon" as const,
  },
  {
    title: "User sessions",
    description: "Monitor user sessions and active authentication state across the system.",
    status: "Coming soon" as const,
  },
  {
    title: "Audit logs",
    description: "Review system audit events and procurement activity logs in a single admin view.",
    status: "Coming soon" as const,
  },
  {
    title: "Master data import/export",
    description: "Load or reset commodity codes, GL accounts, and other shared master data sets.",
    status: "Live" as const,
    href: "/dashboard/admin/master-data",
  },
];

export default function CoreP2PAdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Core P2P Admin</h2>
        <p className="mt-1 text-sm text-slate-500">
          Operational admin screens for users, budget, approvals, and master data.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <AdminActivityCard key={card.title} title={card.title} description={card.description} status={card.status} href={card.href} />
        ))}
      </div>
    </div>
  );
}
