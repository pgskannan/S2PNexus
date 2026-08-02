"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ActAsStartResponse, ActAsStatusResponse, User } from "@/lib/types";

interface StashedSession {
  accessToken: string;
  refreshToken: string | null;
  user: User | null;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  hasHydrated: boolean;
  // Act as User (admin impersonation): originalSession holds the admin's own
  // session while impersonating, so "Exit" can restore it without a
  // re-login. Non-null if and only if currently impersonating -- use it (not
  // a separate flag) to decide whether to show the "Acting as" banner.
  originalSession: StashedSession | null;
  actAs: ActAsStatusResponse | null;
  setSession: (accessToken: string, refreshToken: string) => void;
  setUser: (user: User) => void;
  setActAs: (status: ActAsStatusResponse | null) => void;
  logout: () => void;
  setHasHydrated: (state: boolean) => void;
  startActAs: (response: ActAsStartResponse) => void;
  endActAs: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      hasHydrated: false,
      originalSession: null,
      actAs: null,
      setSession: (accessToken, refreshToken) =>
        // A fresh login always starts clean -- clears out any stale
        // impersonation state left over from a crashed tab/browser close
        // that never hit the normal endActAs()/logout() paths.
        set({ accessToken, refreshToken, originalSession: null, actAs: null }),
      setUser: (user) => set({ user }),
      setActAs: (status) => set({ actAs: status }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          originalSession: null,
          actAs: null,
        }),
      setHasHydrated: (state) => set({ hasHydrated: state }),
      // Stash the current (admin's) session, then swap in the short-lived
      // impersonation token. `user`/full act_as status are left for the
      // caller to populate via a follow-up getMe() call (the start-session
      // response only carries a target-user summary, not the full profile
      // shape the rest of the app expects on `user`).
      startActAs: (response) => {
        const current = get();
        if (!current.accessToken) return;
        set({
          originalSession: {
            accessToken: current.accessToken,
            refreshToken: current.refreshToken,
            user: current.user,
          },
          accessToken: response.access_token,
          refreshToken: null,
          user: null,
          actAs: {
            is_impersonating: true,
            session_id: response.session_id,
            admin_user: response.admin_user,
          },
        });
      },
      endActAs: () => {
        const stashed = get().originalSession;
        if (!stashed) return;
        set({
          accessToken: stashed.accessToken,
          refreshToken: stashed.refreshToken,
          user: stashed.user,
          originalSession: null,
          actAs: null,
        });
      },
    }),
    {
      name: "s2pnexus-auth",
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
