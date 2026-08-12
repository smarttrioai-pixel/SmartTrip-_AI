"use client";

import { useQuery } from "@tanstack/react-query";
import { placesApi } from "@/features/places/data/placesApi";
import type { EnrichPlaceInput } from "@/features/places/domain/types";

/**
 * Batches enrichment for every activity across a trip's days into one
 * request. Keyed by destination + the exact set of activity titles, so it
 * naturally refetches if the underlying trip data changes.
 */
export function useEnrichedPlaces(destination: string, places: EnrichPlaceInput[]) {
  return useQuery({
    queryKey: [\n      "places",\n      "enrich",\n      destination,\n      places.map((p) => [p.title, p.locationHint, p.category, p.mealType, p.foodQuery]),\n    ],
    queryFn: () => placesApi.enrichPlaces(destination, places),
    enabled: places.length > 0,
    staleTime: 30 * 60 * 1000, // real place data (image/rating/address) doesn't change minute to minute
  });
}
