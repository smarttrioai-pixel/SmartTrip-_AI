"use client";

import { useQuery } from "@tanstack/react-query";
import { placesApi } from "@/features/places/data/placesApi";
import type { EnrichPlaceInput } from "@/features/places/domain/types";

/**
 * Batches enrichment for every activity across a trip's days into one
 * request. The query key changes whenever the destination or place inputs
 * change, allowing React Query to cache and refetch real place data safely.
 */
export function useEnrichedPlaces(
  destination: string,
  places: EnrichPlaceInput[],
) {
  return useQuery({
    queryKey: [
      "places",
      "enrich",
      destination,
      places.map((p) => [
        p.title,
        p.locationHint,
        p.category,
        p.mealType,
        p.foodQuery,
      ]),
    ],
    queryFn: () => placesApi.enrichPlaces(destination, places),
    enabled: places.length > 0,
    staleTime: 30 * 60 * 1000,
  });
}
