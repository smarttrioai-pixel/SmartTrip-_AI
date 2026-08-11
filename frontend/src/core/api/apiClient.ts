import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import { getAuth } from "firebase/auth";

import { firebaseApp } from "@/core/config/firebase";

/**
 * Normalized error shape every API call rejects with, so UI code never has
 * to reach into Axios/response internals.
 */
export interface ApiError {
  status: number;
  message: string;
  fieldErrors?: Record<string, string[]>;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// LLM itinerary generation can take 20-60 seconds on Groq free tier.
// Do NOT use 15s here — that causes a premature timeout which then triggers
// a retry, resulting in duplicate Groq requests and rate-limit 429 errors.
const REQUEST_TIMEOUT_MS = 90_000; // 90 seconds

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: { "Content-Type": "application/json" },
});

// --- Request interceptor: attach a fresh Firebase ID token ---
// `getIdToken()` returns the cached token and transparently refreshes it
// in the background before it expires — there is no manual refresh/retry
// dance to implement here, unlike a hand-rolled JWT setup.
apiClient.interceptors.request.use(async (config) => {
  const currentUser = getAuth(firebaseApp).currentUser;
  if (currentUser) {
    const token = await currentUser.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retryCount?: number;
}

// --- Response interceptor: normalize errors ---
// IMPORTANT: We do NOT retry failed requests here.
//
// Rationale for removing automatic retries on POST /trips/generate:
//   - LLM generation requests are expensive (they consume Groq free-tier
//     tokens). An automatic retry after a timeout or network blip would
//     send a duplicate request while the first request might still be
//     running on the server.
//   - This leads to multiple simultaneous Groq requests for the same user
//     action, rapidly exhausting the free-tier token-per-minute limit and
//     causing cascading 429 errors.
//   - React Query's useMutation does NOT automatically retry mutations,
//     which is the correct behaviour for non-idempotent operations.
//   - If a retry is desired, the user can re-click the Generate button
//     (which is disabled while the request is in-flight via isPending).
//
// The previous MAX_RETRIES=2 logic has been removed entirely.
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail?: string | Record<string, string[]> }>) => {
    const normalized: ApiError = {
      status: error.response?.status ?? 0,
      message:
        typeof error.response?.data?.detail === "string"
          ? error.response.data.detail
          : error.code === "ECONNABORTED" || error.message?.includes("timeout")
          ? "The request timed out. The AI is taking longer than expected — please try again."
          : "Something went wrong. Please try again.",
      fieldErrors:
        typeof error.response?.data?.detail === "object"
          ? (error.response.data.detail as Record<string, string[]>)
          : undefined,
    };

    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("[API Error]", normalized, error);
    }

    return Promise.reject(normalized);
  }
);
