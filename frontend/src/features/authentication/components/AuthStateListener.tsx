"use client";

import { useQueryClient } from "@tanstack/react-query";
import { getAuth, onIdTokenChanged } from "firebase/auth";
import { useEffect } from "react";

import { firebaseApp } from "@/core/config/firebase";
import { authApi } from "@/features/authentication/data/authApi";
import { useAuthStore } from "@/features/authentication/store/authStore";

/**
 * Mounted once near the root of the app. Firebase restores the signed-in
 * user from IndexedDB asynchronously on page load and fires this listener —
 * that's the actual source of truth for "is logged in", not anything we
 * persist ourselves. This component's only job is to mirror that state into
 * the Zustand store (for the sidebar/session-cookie/middleware to read) and
 * fetch the matching Firestore profile.
 */
export function AuthStateListener() {
  const setUser = useAuthStore((s) => s.setUser);
  const clearUser = useAuthStore((s) => s.clearUser);
  const setIsHydrated = useAuthStore((s) => s.setIsHydrated);
  const queryClient = useQueryClient();

  useEffect(() => {
    const unsubscribe = onIdTokenChanged(getAuth(firebaseApp), async (firebaseUser) => {
      if (firebaseUser) {
        try {
          const profile = await authApi.getCurrentProfile();
          setUser(profile);
        } catch {
          // Backend unreachable or token rejected — treat as logged out
          // rather than leaving stale profile data in the store.
          clearUser();
        }
      } else {
        clearUser();
        queryClient.clear();
      }
      setIsHydrated(true);
    });

    return unsubscribe;
  }, [setUser, clearUser, setIsHydrated, queryClient]);

  return null;
}
