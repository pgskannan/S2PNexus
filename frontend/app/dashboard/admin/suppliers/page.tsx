import AdminActivityCard from "@/components/AdminActivityCard";

const cards = [
  {
    title: "Onboarding & mass actions",
    description: "Import and manage supplier onboarding actions and bulk invites.",
    status: "Coming soon" as const,
  },
  {
    title: "Questionnaire engine",
    description: "Build and manage supplier questionnaires and onboarding questionnaires.",
    status: "Coming soon" as const,
  },
  {
    title: "Lifecycle & Status Rules",
    description: "Manage supplier lifecycle transitions and status rules for active suppliers.",
    status: "Live" as const,
    href: "/dashboard/suppliers",
  },
  {
    title: "Preferred Supplier Management",
    description:
      "Composite scoring (qualification, performance, risk, spend), auto-classification, and reviewed manual overrides.",
    status: "Live" as const,
    href: "/dashboard/admin/preferred-suppliers",
  },
  {
    title: "Project/template version control",
    description: "Track supplier onboarding templates and project iterations over time.",
    status: "Coming soon" as const,
  },
  {
    title: "ERP integration sync",
    description: "Sync supplier and procurement data to external ERP systems.",
    status: "Coming soon" as const,
  },
  {
    title: "Supplier analytics / reporting export",
    description: "Export supplier onboarding and performance analytics to reports.",
    status: "Coming soon" as const,
  },
];

export default function SuppliersAdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Supplier Management Admin</h2>
        <p className="mt-1 text-sm text-slate-500">
          Supplier lifecycle, onboarding, and analytics administration in one place.
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
