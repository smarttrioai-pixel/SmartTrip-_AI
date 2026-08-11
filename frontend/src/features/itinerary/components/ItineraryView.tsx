"use client";

import { Bookmark, BookmarkCheck } from "lucide-react";

import { useSetTripSaved } from "@/features/itinerary/hooks/useTrips";
import type { Trip } from "@/features/itinerary/domain/types";
import { useEnrichedPlaces } from "@/features/places/hooks/usePlaceEnrichment";
import { PlaceCard } from "@/features/places/components/PlaceCard";
import { Button } from "@/shared/components/ui/button";

export function ItineraryView({ trip }: { trip: Trip }) {
  const setSaved = useSetTripSaved();

  // One batched enrichment request for every activity across every day —
  // not one request per card, to keep this to a single round trip.
  const allActivities = (trip.days ?? []).flatMap((day) => day.activities);
  const { data: enrichedPlaces, isLoading: isEnriching } = useEnrichedPlaces(
    trip.destination,
    allActivities.map((a) => ({ title: a.title, locationHint: a.location }))
  );

  let activityIndex = 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800">
        <div>
          <h2 className="font-display text-xl font-semibold text-ink-900 dark:text-white">{trip.destination}</h2>
          <p className="mt-1 text-sm text-ink-400">
            {trip.startDate} — {trip.endDate} · {trip.travelStyle} style
          </p>
          <p className="mt-1 text-sm font-medium text-brand-600">
            Estimated cost: {(trip.estimatedTotalCost ?? 0).toLocaleString()} {trip.currency}
            <span className="ml-1 font-normal text-ink-400">(budget: {(trip.budget ?? 0).toLocaleString()})</span>
          </p>
        </div>
        <Button
          variant="outline"
          isLoading={setSaved.isPending}
          onClick={() => setSaved.mutate({ tripId: trip.id, isSaved: !trip.isSaved })}
        >
          {trip.isSaved ? <BookmarkCheck className="h-4 w-4" /> : <Bookmark className="h-4 w-4" />}
          {trip.isSaved ? "Saved" : "Save trip"}
        </Button>
      </div>

      {(trip.days ?? []).map((day) => (
        <div key={day.dayNumber} className="rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800">
          <h3 className="font-display text-lg font-semibold text-ink-900 dark:text-white">
            Day {day.dayNumber}: {day.title}
          </h3>
          <div className="mt-4 flex flex-col gap-3">
            {day.activities.map((activity, i) => {
              const enrichment = enrichedPlaces?.[activityIndex];
              activityIndex += 1;
              return (
                <PlaceCard
                  key={i}
                  title={activity.title}
                  time={activity.time}
                  description={activity.description}
                  location={activity.location}
                  aiEstimatedCost={activity.estimatedCost ?? 0}
                  currency={trip.currency}
                  enrichment={enrichment}
                  isEnrichmentLoading={isEnriching}
                  explanation={activity.explanation}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
