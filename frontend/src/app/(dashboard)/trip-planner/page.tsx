"use client";

import { useState } from "react";

import { TripPlannerForm } from "@/features/itinerary/components/TripPlannerForm";
import { ItineraryView } from "@/features/itinerary/components/ItineraryView";
import { ScifGenerationProgress } from "@/features/itinerary/components/ScifGenerationProgress";
import type { Trip } from "@/features/itinerary/domain/types";

export default function TripPlannerPage() {
  const [generatedTrip, setGeneratedTrip] = useState<Trip | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationComplete, setGenerationComplete] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);

  const handleGenerationStart = () => {
    setGeneratedTrip(null);
    setGenerationComplete(false);
    setGenerationError(null);
    setIsGenerating(true);
  };

  const handleGenerated = (trip: Trip) => {
    setGenerationComplete(true);
    // Short delay so user sees all steps tick ✓ before the itinerary appears
    setTimeout(() => {
      setIsGenerating(false);
      setGeneratedTrip(trip);
    }, 1200);
  };

  const handleGenerationError = (message: string) => {
    setGenerationError(message);
    setGenerationComplete(true);
    setIsGenerating(false);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">
        AI Trip Planner
      </h1>
      <p className="mt-1 text-sm text-ink-400 dark:text-ink-500">
        SmartTrip uses the SCIF pipeline — memory, agents, live context, and AI reasoning — to
        build a personalised day-by-day itinerary with verified real places.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[400px_1fr]">
        {/* Left: form */}
        <div className="flex flex-col gap-5">
          <div className="rounded-2xl border border-ink-100 bg-white p-6 shadow-sm dark:border-ink-700 dark:bg-ink-800">
            <TripPlannerForm
              onGenerationStart={handleGenerationStart}
              onGenerated={handleGenerated}
              onGenerationError={handleGenerationError}
            />
          </div>

          {/* SCIF progress — shown when generating */}
          {isGenerating && (
            <ScifGenerationProgress
              isVisible={isGenerating}
              isComplete={generationComplete}
              error={generationError}
            />
          )}
        </div>

        {/* Right: itinerary or placeholder */}
        <div>
          {generatedTrip ? (
            <ItineraryView trip={generatedTrip} />
          ) : !isGenerating ? (
            <div className="flex h-full min-h-[400px] flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-ink-100 p-8 text-center dark:border-ink-700">
              <div className="rounded-2xl bg-brand-50 p-4 dark:bg-brand-900/20">
                <svg
                  className="h-8 w-8 text-brand-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
                  />
                </svg>
              </div>
              <div>
                <p className="font-medium text-ink-700 dark:text-ink-300">
                  Your itinerary will appear here
                </p>
                <p className="mt-1 text-sm text-ink-400 dark:text-ink-500">
                  Fill in the form and click Generate to build your personalised trip.
                </p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
