import { FirebaseError } from "firebase/app";

import type { ApiError } from "@/core/api/apiClient";

const MESSAGES: Record<string, string> = {
  "auth/email-already-in-use": "An account with this email already exists.",
  "auth/invalid-credential": "Incorrect email or password.",
  "auth/invalid-email": "Enter a valid email address.",
  "auth/wrong-password": "Incorrect email or password.",
  "auth/user-not-found": "No account found with that email.",
  "auth/weak-password": "Choose a stronger password.",
  "auth/too-many-requests": "Too many attempts. Please wait a moment and try again.",
  "auth/popup-closed-by-user": "Google sign-in was cancelled.",
  "auth/network-request-failed": "Network error. Check your connection and try again.",
};

/** Normalizes any error thrown during auth (Firebase or our own API calls) into ApiError. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof FirebaseError) {
    return { status: 0, message: MESSAGES[error.code] ?? "Something went wrong. Please try again." };
  }
  if (typeof error === "object" && error !== null && "message" in error && "status" in error) {
    return error as ApiError; // already normalized, e.g. thrown by apiClient's interceptor
  }
  return { status: 0, message: "Something went wrong. Please try again." };
}
