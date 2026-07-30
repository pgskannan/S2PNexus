"use client";

// Ported from the user's other project
// (components/enterprise/ActionRecommendationStrip.tsx), unchanged aside from
// dropping the private/team scope toggle (S2PNexus has no equivalent concept
// yet) -- a small banner surfacing counts + one-click filters plus a short
// recommendation line.

import Link from "next/link";

type ActionTone = "critical" | "warning" | "neutral";

type StripAction = {
  label: string;
  count?: number;
  tone?: ActionTone;
  onClick?: () => void;
  href?: string;
};

interface ActionRecommendationStripProps {
  title: string;
  description: string;
  recommendation: string;
  actions: StripAction[];
}

export default function ActionRecommendationStrip({
  title,
  description,
  recommendation,
  actions,
}: ActionRecommendationStripProps) {
  const toneClass = (tone: ActionTone | undefined) => {
    if (tone === "critical") return "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100";
    if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100";
    return "border-slate-200 bg-white text-slate-700 hover:bg-slate-50";
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{title}</div>
        <div className="mt-1 text-sm text-slate-600">{description}</div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {actions.map((action) => {
          const content = (
            <>
              <span>{action.label}</span>
              {typeof action.count === "number" ? (
                <span className="rounded-full bg-white px-2 py-0.5 text-xs font-semibold">{action.count}</span>
              ) : null}
            </>
          );
          if (action.href) {
            return (
              <Link
                key={`${action.label}-${action.href}`}
                href={action.href}
                className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${toneClass(action.tone)}`}
              >
                {content}
              </Link>
            );
          }
          return (
            <button
              key={action.label}
              type="button"
              onClick={action.onClick}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${toneClass(action.tone)}`}
            >
              {content}
            </button>
          );
        })}
      </div>

      <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900">
        <div className="font-semibold uppercase tracking-wide">Triage recommendation</div>
        <div className="mt-1">{recommendation}</div>
      </div>
    </div>
  );
}
