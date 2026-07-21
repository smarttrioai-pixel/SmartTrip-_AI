"use client";

import { useState } from "react";

import { TripPlannerForm } from "@/features/itinerary/components/TripPlannerForm";
import { ItineraryView } from "@/features/itinerary/components/ItineraryView";
import type { Trip } from "@/features/itinerary/domain/types";

export default function TripPlannerPage() {
  const [generatedTrip, setGeneratedTrip] = useState<Trip | null>(null);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">AI Trip Planner</h1>
      <p className="mt-1 text-sm text-ink-400">
        Tell us where you're headed and we'll build a day-by-day itinerary.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[380px_1fr]">
        <div className="rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800">
          <TripPlannerForm onGenerated={setGeneratedTrip} />
        </div>

        <div>
          {generatedTrip ? (
            <ItineraryView trip={generatedTrip} />
          ) : (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-2xl border border-dashed border-ink-100 p-8 text-center text-sm text-ink-400 dark:border-ink-700">
              Fill out the form to generate your itinerary.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
