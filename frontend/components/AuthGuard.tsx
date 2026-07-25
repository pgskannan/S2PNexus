"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth-store";
import { getMe } from "@/lib/api";

export default function AuthGuard({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { accessToken, user, hasHydrated, setUser, logout } = useAuthStore();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!hasHydrated) return;

    if (!accessToken) {
      router.replace("/login");
      return;
    }

    if (user) {
      setChecked(true);
      return;
    }

    getMe(accessToken)
      .then((profile) => {
        setUser(profile);
        setChecked(true);
      })
      .catch(() => {
        logout();
        router.replace("/login");
      });
  }, [hasHydrated, accessToken, user, router, setUser, logout]);

  if (!hasHydrated || !checked) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Checking session...
      </div>
    );
  }

  return <>{children}</>;
}
