import AdminActivityCard from "@/components/AdminActivityCard";

const cards = [
  {
    title: "RFx/auction templates",
    description: "Create and manage reusable RFx or auction templates for sourcing events.",
    status: "Coming soon" as const,
  },
  {
    title: "Contract clause library",
    description: "Maintain standard contract clauses and clause libraries for agreements.",
    status: "Coming soon" as const,
  },
  {
    title: "Standardized workflow conditions",
    description: "Reuse workflow conditions across sourcing, contracts, and approval flows.",
    status: "Live" as const,
    href: "/dashboard/workflow/definitions",
  },
  {
    title: "Sourcing/contract permission scope",
    description: "Assign sourcing and contract permissions through user roles and access policies.",
    status: "Live" as const,
    href: "/dashboard/admin/users",
  },
  {
    title: "Custom fields / scoring rules for RFx",
    description: "Configure custom RFx scoring rules and sourcing field definitions.",
    status: "Live" as const,
    href: "/dashboard/admin/templates",
  },
  {
    title: "Sync awarded events/contracts → PO/catalog",
    description: "Automatically sync sourcing awards into purchase orders and catalog records.",
    status: "Coming soon" as const,
  },
];

export default function SourcingAdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Sourcing & Contracts Admin</h2>
        <p className="mt-1 text-sm text-slate-500">
          Sourcing and contract admin capabilities, with links to existing workflow tools.
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
