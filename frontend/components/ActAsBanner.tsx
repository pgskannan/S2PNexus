"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { endActAsSessionRequest, extractErrorMessage } from "@/lib/api";

// Persistent banner shown while an administrator is impersonating another
// user (see lib/auth-store.ts startActAs/endActAs and
// app/dashboard/admin/users/page.tsx for the entry point). Renders nothing
// unless actAs.is_impersonating is true, i.e. originalSession is populated.
export default function ActAsBanner() {
  const router = useRouter();
  const { user, actAs, originalSession, endActAs } = useAuthStore();
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!actAs?.is_impersonating || !originalSession) {
    return null;
  }

  async function handleExit() {
    setEnding(true);
    setError(null);
    try {
      if (actAs?.session_id) {
        // Best-effort -- if the session already expired/was ended
        // server-side this 404s/400s, which shouldn't block exiting locally.
        await endActAsSessionRequest(actAs.session_id).catch(() => undefined);
      }
      endActAs();
      router.replace("/dashboard/admin/users");
      router.refresh();
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setEnding(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 bg-amber-500 px-6 py-2 text-sm font-medium text-amber-950">
      <span>
        Acting as <strong>{user?.full_name ?? "..."}</strong>
        {user?.email ? ` (${user.email})` : ""} -- started by {actAs.admin_user?.full_name ?? "an administrator"}.
        {error && <span className="ml-2 font-normal text-amber-900">{error}</span>}
      </span>
      <button
        onClick={() => void handleExit()}
        disabled={ending}
        className="rounded-md border border-amber-950/30 bg-amber-950/10 px-3 py-1 text-xs font-semibold hover:bg-amber-950/20 disabled:opacity-60"
      >
        {ending ? "Exiting..." : "Exit"}
      </button>
    </div>
  );
}
