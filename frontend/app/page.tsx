"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";

export default function RootPage() {
  const router = useRouter();
  const { accessToken, hasHydrated } = useAuthStore();

  useEffect(() => {
    if (!hasHydrated) return;
    router.replace(accessToken ? "/dashboard" : "/login");
  }, [hasHydrated, accessToken, router]);

  return (
    <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
      Loading S2PNexus...
    </div>
  );
}
