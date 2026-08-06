"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/core/api/apiClient";
import { memoryApi } from "@/features/memory/data/memoryApi";

const MEMORY_QUERY_KEY = ["memory", "insights"];

export function useMemoryInsights() {
  return useQuery({
    queryKey: MEMORY_QUERY_KEY,
    queryFn: memoryApi.getInsights,
    staleTime: 60 * 1000,
  });
}

export function useSavePreference() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: memoryApi.savePreference,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MEMORY_QUERY_KEY }),
  });
}

export function useRejectInference() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: memoryApi.rejectInference,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MEMORY_QUERY_KEY }),
  });
}
