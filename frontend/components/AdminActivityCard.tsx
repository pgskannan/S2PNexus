import Link from "next/link";
import type { ReactNode } from "react";

interface AdminActivityCardProps {
  title: string;
  description: string;
  status: "Live" | "Coming soon";
  href?: string;
  children?: ReactNode;
}

export default function AdminActivityCard({ title, description, status, href, children }: AdminActivityCardProps) {
  const content = (
    <div className="card flex h-full flex-col justify-between gap-4">
      <div>
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
              status === "Live"
                ? "bg-emerald-100 text-emerald-700"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {status}
          </span>
        </div>
        <p className="mt-3 text-sm text-slate-500">{description}</p>
      </div>
      {children}
    </div>
  );

  if (href && status === "Live") {
    return (
      <Link href={href} className="block hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500">
        {content}
      </Link>
    );
  }

  return content;
}
