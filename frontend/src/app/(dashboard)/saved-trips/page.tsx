"use client";

import { MapPinned, Trash2 } from "lucide-react";
import { useState } from "react";

import { useDeleteTrip, useTrips } from "@/features/itinerary/hooks/useTrips";
import { ItineraryView } from "@/features/itinerary/components/ItineraryView";
import type { Trip } from "@/features/itinerary/domain/types";

export default function SavedTripsPage() {
  const { data: trips, isLoading } = useTrips(true);
  const deleteTrip = useDeleteTrip();
  const [selectedTrip, setSelectedTrip] = useState<Trip | null>(null);

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">Saved Trips</h1>
      <p className="mt-1 text-sm text-ink-400">
        Trips you've bookmarked from the AI Trip Planner. Map view (Module 13, MapLibre) is a later phase —
        this is the list view for now.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[300px_1fr]">
        <div className="flex flex-col gap-3">
          {isLoading && <p className="text-sm text-ink-400">Loading…</p>}
          {!isLoading && trips?.length === 0 && (
            <p className="rounded-2xl border border-dashed border-ink-100 p-6 text-center text-sm text-ink-400 dark:border-ink-700">
              No saved trips yet. Save one from the Trip Planner.
            </p>
          )}
          {trips?.map((trip) => (
            <button
              key={trip.id}
              onClick={() => setSelectedTrip(trip)}
              className={`flex items-center justify-between gap-2 rounded-xl border p-4 text-left transition-colors ${
                selectedTrip?.id === trip.id
                  ? "border-brand-500 bg-brand-50 dark:bg-brand-900/20"
                  : "border-ink-100 bg-white hover:bg-ink-50 dark:border-ink-700 dark:bg-ink-800 dark:hover:bg-ink-800/60"
              }`}
            >
              <div>
                <p className="font-medium text-ink-900 dark:text-white">{trip.destination}</p>
                <p className="text-xs text-ink-400">
                  {trip.startDate} — {trip.endDate}
                </p>
              </div>
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  deleteTrip.mutate(trip.id);
                  if (selectedTrip?.id === trip.id) setSelectedTrip(null);
                }}
                className="shrink-0 rounded-lg p-1.5 text-ink-400 hover:bg-sunset-50 hover:text-sunset-600"
                aria-label={`Delete trip to ${trip.destination}`}
              >
                <Trash2 className="h-4 w-4" />
              </span>
            </button>
          ))}
        </div>

        <div>
          {selectedTrip ? (
            <ItineraryView trip={selectedTrip} />
          ) : (
            <div className="flex min-h-[300px] flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-ink-100 p-8 text-center text-sm text-ink-400 dark:border-ink-700">
              <MapPinned className="h-8 w-8" />
              Select a trip to view its itinerary.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
