import AdminActivityCard from "@/components/AdminActivityCard";

const cards = [
  {
    title: "Data import/export engine",
    description: "Unified master-data import/export and reset capabilities for the platform.",
    status: "Live" as const,
    href: "/dashboard/admin/master-data",
  },
  {
    title: "System integration hub",
    description: "Manage webhooks, API connectors, and ERP integration endpoints.",
    status: "Coming soon" as const,
  },
  {
    title: "Definition control (schema/mapping/transform rules)",
    description: "Define schema mappings and transform rules for inbound integrations.",
    status: "Coming soon" as const,
  },
];

export default function PlatformDataAdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Platform & Data Admin</h2>
        <p className="mt-1 text-sm text-slate-500">
          Platform and integration administration, with master-data upload/extract as the central hub.
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
