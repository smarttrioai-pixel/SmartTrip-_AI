"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  getAuth,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
  updateProfile as updateFirebaseProfile,
} from "firebase/auth";
import { useRouter } from "next/navigation";

import type { ApiError } from "@/core/api/apiClient";
import { firebaseApp } from "@/core/config/firebase";
import { authApi } from "@/features/authentication/data/authApi";
import { toApiError } from "@/features/authentication/domain/firebaseErrors";
import { useAuthStore } from "@/features/authentication/store/authStore";
import type { LoginPayload, SignupPayload } from "@/features/authentication/domain/types";

const auth = () => getAuth(firebaseApp);

/** Email/password signup via Firebase, then syncs the display name to our Firestore profile. */
export function useSignup() {
  const setUser = useAuthStore((s) => s.setUser);
  const router = useRouter();

  return useMutation<void, ApiError, SignupPayload>({
    mutationFn: async (payload) => {
      try {
        const credential = await createUserWithEmailAndPassword(auth(), payload.email, payload.password);
        await updateFirebaseProfile(credential.user, { displayName: payload.fullName });
        const user = await authApi.syncProfile(payload.fullName);
        setUser(user);
      } catch (error) {
        throw toApiError(error);
      }
    },
    onSuccess: () => router.replace("/home"),
  });
}

/** Email/password login via Firebase. */
export function useLogin() {
  const setUser = useAuthStore((s) => s.setUser);
  const router = useRouter();

  return useMutation<void, ApiError, LoginPayload>({
    mutationFn: async (payload) => {
      try {
        await signInWithEmailAndPassword(auth(), payload.email, payload.password);
        const user = await authApi.syncProfile();
        setUser(user);
      } catch (error) {
        throw toApiError(error);
      }
    },
    onSuccess: () => router.replace("/home"),
  });
}

/** "Continue with Google" — popup sign-in, no arguments needed. */
export function useGoogleLogin() {
  const setUser = useAuthStore((s) => s.setUser);
  const router = useRouter();

  return useMutation<void, ApiError, void>({
    mutationFn: async () => {
      try {
        const provider = new GoogleAuthProvider();
        const credential = await signInWithPopup(auth(), provider);
        const user = await authApi.syncProfile(credential.user.displayName ?? undefined);
        setUser(user);
      } catch (error) {
        throw toApiError(error);
      }
    },
    onSuccess: () => router.replace("/home"),
  });
}

export function useForgotPassword() {
  return useMutation<void, ApiError, string>({
    mutationFn: async (email) => {
      try {
        await sendPasswordResetEmail(auth(), email);
      } catch (error) {
        throw toApiError(error);
      }
    },
  });
}

/** Fetches the current profile from our backend; disabled until a session exists. */
export function useCurrentUser() {
  const isAuthenticated = useAuthStore((s) => Boolean(s.user));
  return useQuery({
    queryKey: ["profile"],
    queryFn: authApi.getCurrentProfile,
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLogout() {
  const clearUser = useAuthStore((s) => s.clearUser);
  const queryClient = useQueryClient();
  const router = useRouter();

  return () => {
    void signOut(auth());
    clearUser();
    queryClient.clear();
    router.replace("/login");
  };
}
