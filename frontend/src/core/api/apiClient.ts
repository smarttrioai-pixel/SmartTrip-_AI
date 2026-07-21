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
const MAX_RETRIES = 2;

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 15_000,
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

// --- Response interceptor: normalize errors, retry transient network errors ---
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail?: string | Record<string, string[]> }>) => {
    const config = error.config as RetryableConfig | undefined;

    // Retry transient network errors (no response received) with backoff.
    if (!error.response && config) {
      config._retryCount = (config._retryCount ?? 0) + 1;
      if (config._retryCount <= MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, 300 * config._retryCount!));
        return apiClient.request(config);
      }
    }

    const normalized: ApiError = {
      status: error.response?.status ?? 0,
      message:
        typeof error.response?.data?.detail === "string"
          ? error.response.data.detail
          : "Something went wrong. Please try again.",
      fieldErrors:
        typeof error.response?.data?.detail === "object" ? (error.response.data.detail as Record<string, string[]>) : undefined,
    };

    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("[API Error]", normalized, error);
    }

    return Promise.reject(normalized);
  }
);
