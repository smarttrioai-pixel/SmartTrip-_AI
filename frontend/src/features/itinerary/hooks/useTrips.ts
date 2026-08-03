"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiError } from "@/core/api/apiClient";
import { tripApi } from "@/features/itinerary/data/tripApi";
import type { GenerateItineraryPayload, Trip } from "@/features/itinerary/domain/types";

const TRIPS_QUERY_KEY = ["trips"];

export function useTrips(savedOnly = false) {
  return useQuery({
    queryKey: [...TRIPS_QUERY_KEY, { savedOnly }],
    queryFn: () => tripApi.list(savedOnly),
    staleTime: 60 * 1000,
  });
}

export function useGenerateItinerary() {
  const queryClient = useQueryClient();
  return useMutation<Trip, ApiError, GenerateItineraryPayload>({
    mutationFn: tripApi.generate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TRIPS_QUERY_KEY }),
  });
}

export function useSetTripSaved() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, { tripId: string; isSaved: boolean }>({
    mutationFn: ({ tripId, isSaved }) => tripApi.setSaved(tripId, isSaved),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TRIPS_QUERY_KEY }),
  });
}

export function useDeleteTrip() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (tripId) => tripApi.remove(tripId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TRIPS_QUERY_KEY }),
  });
}
