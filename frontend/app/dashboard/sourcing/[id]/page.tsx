"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { getSourcingEvent, extractErrorMessage } from "@/lib/api";
import type { SourcingEvent } from "@/lib/types";
import InviteSuppliersCard from "@/components/InviteSuppliersCard";

export default function SourcingDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [event, setEvent] = useState<SourcingEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await getSourcingEvent(params.id);
      setEvent(data);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  if (error && !event) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  if (!event) {
    return <p className="text-sm text-slate-400">Loading...</p>;
  }

  return (
    <div className="max-w-3xl space-y-6">
      <button
        onClick={() => router.push("/dashboard/sourcing")}
        className="text-sm text-brand-600 hover:underline"
      >
        &larr; Back to sourcing
      </button>

      <div className="card space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-semibold">{event.title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {event.description || "No description"}
            </p>
          </div>
          <span className="badge bg-slate-100 text-slate-700 uppercase">
            {event.status}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-slate-500">Event number</dt>
            <dd>{event.event_number}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Event type</dt>
            <dd>{event.event_type}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Category</dt>
            <dd>{event.category || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Estimated value</dt>
            <dd>{event.estimated_value ? `${event.currency} ${event.estimated_value}` : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Response due</dt>
            <dd>{event.response_due_date ? new Date(event.response_due_date).toLocaleDateString() : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Line items</dt>
            <dd>{event.line_items.length}</dd>
          </div>
        </dl>

        {/* Preferred-supplier recommendation nudge (Template Framework Phase 5) */}
        <InviteSuppliersCard event={event} onInvited={() => void load()} />

        <div className="rounded-lg border border-slate-200 p-4">
          <h2 className="font-semibold">Line items</h2>
          {event.line_items.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No line items yet.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {event.line_items.map((item) => (
                <li key={item.id} className="rounded bg-slate-50 p-2">
                  {item.description}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
