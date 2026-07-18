import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { User } from "@/features/authentication/domain/types";

/**
 * Presence-only cookie (no token material — Firebase's own SDK persistence
 * in IndexedDB is the real session store) so the edge `middleware.ts` can
 * cheaply decide whether to redirect.
 */
function setSessionCookie(present: boolean) {
  if (typeof document === "undefined") return;
  document.cookie = present
    ? "smarttrip-session=1; path=/; max-age=2592000; samesite=lax"
    : "smarttrip-session=; path=/; max-age=0";
}

interface AuthState {
  user: User | null;
  isHydrated: boolean;
  setUser: (user: User) => void;
  clearUser: () => void;
  setIsHydrated: (value: boolean) => void;
}

/**
 * This store mirrors the *result* of Firebase's auth state (via
 * AuthStateListener's onIdTokenChanged subscription) — it is not itself the
 * source of truth for whether the user is logged in. `isHydrated` flips true
 * once that first `onIdTokenChanged` callback has fired, so the UI can avoid
 * a flash of "logged out" while Firebase restores the session on page load.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isHydrated: false,

      setUser: (user) => {
        setSessionCookie(true);
        set({ user });
      },

      clearUser: () => {
        setSessionCookie(false);
        set({ user: null });
      },

      setIsHydrated: (value) => set({ isHydrated: value }),
    }),
    {
      name: "smarttrip-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ user: state.user }),
    }
  )
);
