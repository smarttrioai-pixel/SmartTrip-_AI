"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/core/api/apiClient";
import { profileApi } from "@/features/profile/data/profileApi";
import type { UserPreferences } from "@/features/profile/domain/types";

const PROFILE_QUERY_KEY = ["profile"];

export function useProfile() {
  return useQuery({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: profileApi.getProfile,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateFullName() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: async (fullName) => {
      const profile = await profileApi.updateFullName(fullName);
      queryClient.setQueryData(PROFILE_QUERY_KEY, profile);
    },
  });
}

export function useUpdatePreferences() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, UserPreferences>({
    mutationFn: async (preferences) => {
      const profile = await profileApi.updatePreferences(preferences);
      queryClient.setQueryData(PROFILE_QUERY_KEY, profile);
    },
  });
}
