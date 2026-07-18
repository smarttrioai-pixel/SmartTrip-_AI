"use client";

import { Bookmark, BookmarkCheck, Clock, MapPin } from "lucide-react";

import { useSetTripSaved } from "@/features/itinerary/hooks/useTrips";
import type { Trip } from "@/features/itinerary/domain/types";
import { Button } from "@/shared/components/ui/button";

export function ItineraryView({ trip }: { trip: Trip }) {
  const setSaved = useSetTripSaved();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800">
        <div>
          <h2 className="font-display text-xl font-semibold text-ink-900 dark:text-white">{trip.destination}</h2>
          <p className="mt-1 text-sm text-ink-400">
            {trip.startDate} — {trip.endDate} · {trip.travelStyle} style
          </p>
          <p className="mt-1 text-sm font-medium text-brand-600">
            Estimated cost: {trip.estimatedTotalCost.toLocaleString()} {trip.currency}
            <span className="ml-1 font-normal text-ink-400">(budget: {trip.budget.toLocaleString()})</span>
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

      {trip.days.map((day) => (
        <div key={day.dayNumber} className="rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800">
          <h3 className="font-display text-lg font-semibold text-ink-900 dark:text-white">
            Day {day.dayNumber}: {day.title}
          </h3>
          <div className="mt-4 flex flex-col gap-4">
            {day.activities.map((activity, i) => (
              <div key={i} className="flex gap-4 border-l-2 border-brand-100 pl-4 dark:border-brand-900/40">
                <div className="flex w-20 shrink-0 items-center gap-1.5 text-xs font-medium text-ink-400">
                  <Clock className="h-3.5 w-3.5" />
                  {activity.time}
                </div>
                <div className="flex-1">
                  <p className="font-medium text-ink-900 dark:text-white">{activity.title}</p>
                  <p className="mt-0.5 text-sm text-ink-400">{activity.description}</p>
                  <div className="mt-1.5 flex items-center gap-3 text-xs text-ink-400">
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" /> {activity.location}
                    </span>
                    <span>
                      ~{activity.estimatedCost.toLocaleString()} {trip.currency}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
