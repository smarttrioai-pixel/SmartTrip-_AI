"use client";

import { useState } from "react";
import {
  Bookmark,
  BookmarkCheck,
  MapPin,
  Calendar,
  Wallet,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { useSetTripSaved } from "@/features/itinerary/hooks/useTrips";
import type { Trip } from "@/features/itinerary/domain/types";
import { useEnrichedPlaces } from "@/features/places/hooks/usePlaceEnrichment";
import { ActivityCard } from "@/features/itinerary/components/ActivityCard";
import { ScifIntelligencePanel } from "@/features/itinerary/components/ScifIntelligencePanel";
import { useFeedback } from "@/features/itinerary/hooks/useFeedback";
import { Button } from "@/shared/components/ui/button";
import { PlannerChat } from "@/features/itinerary/components/PlannerChat";
import { AlternativePanel } from "@/features/itinerary/components/AlternativePanel";
import { useAlternatives, useRemoveActivity, useMoveActivity, useReplaceActivity } from "@/features/itinerary/hooks/useItineraryActions";
import type { Activity, ActivityAlternative, ModifyItineraryResponse } from "@/features/itinerary/domain/types";


export function ItineraryView({ trip }: { trip: Trip }) {
  const setSaved = useSetTripSaved();
  const [activeDayIndex, setActiveDayIndex] = useState(0);

  // Per-activity feedback — tied to this trip's ID.
  // Passes feedback state and submitFeedback down to each ActivityCard.
  const { submitFeedback, getFeedbackState } = useFeedback(trip.id);

  const days = trip.days ?? [];
  const activeDay = days[activeDayIndex];

  // Itinerary Actions
  const [alternativesActivity, setAlternativesActivity] = useState<{activity: Activity, dayNumber: number} | null>(null);
  const [alternatives, setAlternatives] = useState<ActivityAlternative[]>([]);
  const getAlternativesMutation = useAlternatives();
  const removeMutation = useRemoveActivity(trip.id);
  const moveMutation = useMoveActivity(trip.id);
  const replaceMutation = useReplaceActivity(trip.id);

  const handleGetAlternatives = (activity: Activity, dayNumber: number) => {
    if (!activity.id) return;
    setAlternativesActivity({ activity, dayNumber });
    getAlternativesMutation.mutate(
      { tripId: trip.id, activityId: activity.id, dayNumber },
      {
        onSuccess: (res) => {
          setAlternatives(res.alternatives);
        }
      }
    );
  };

  const handleRemove = (activityId: string, dayNumber: number) => {
    removeMutation.mutate({ activityId, dayNumber });
  };

  const handleMove = (activityId: string, fromDay: number, toDay: number, newTime: string) => {
    moveMutation.mutate({
      activityId,
      payload: { activity_id: activityId, from_day: fromDay, to_day: toDay, new_time: newTime }
    });
  };

  const handleReplace = (alt: ActivityAlternative) => {
    if (!alternativesActivity?.activity?.id) return;
    replaceMutation.mutate(
      {
        activityId: alternativesActivity.activity.id,
        payload: {
          activity_id: alternativesActivity.activity.id,
          day_number: alternativesActivity.dayNumber,
          place_id: alt.place_id,
          alternative_title: alt.title,
        }
      },
      {
        onSuccess: () => {
          setAlternativesActivity(null);
          setAlternatives([]);
        }
      }
    );
  };

  const handleModification = (res: ModifyItineraryResponse) => {
    if (res.conflict) {
      alert(`Conflict: ${res.conflict}`);
    } else {
      alert(`Success: ${res.message}`);
    }
  };

  // Batch-enrich ALL activities (one request, matches by position).
  // Provides Geoapify enrichment on top of whatever inline place_enrichment
  // the backend already embedded in the trip response.
  const allActivities = days.flatMap((day) => day.activities);
  const { data: enrichedPlaces, isLoading: isEnriching } = useEnrichedPlaces(
    trip.destination,
    allActivities.map((a) => ({
      title: a.title,
      locationHint: a.location,
      category: a.category ?? undefined,
      mealType: a.mealType ?? undefined,
      foodQuery: a.foodQuery ?? undefined,
    }))
  );

  // Map each day's activities to their flat index for enrichment lookup
  let globalIndex = 0;
  const dayActivityIndexMap = days.map((day) => {
    const start = globalIndex;
    globalIndex += day.activities.length;
    return start;
  });

  const numDays = days.length;

  return (
    <div className="flex flex-col gap-5">
      {/* Trip header */}
      <div className="flex flex-col gap-3 rounded-2xl border border-ink-100 bg-white p-5 shadow-sm dark:border-ink-700 dark:bg-ink-800 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex-1 min-w-0">
          <h2 className="font-display text-xl font-semibold text-ink-900 dark:text-white truncate">
            {trip.destination}
          </h2>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-400 dark:text-ink-500">
            <span className="flex items-center gap-1">
              <Calendar className="h-3.5 w-3.5 shrink-0" />
              {trip.startDate} — {trip.endDate}
            </span>
            <span className="capitalize">{trip.travelStyle} style</span>
            <span className="flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5 shrink-0" />
              {numDays} day{numDays !== 1 ? "s" : ""}
            </span>
            <span className="flex items-center gap-1 text-brand-600 dark:text-brand-400 font-medium">
              <Wallet className="h-3.5 w-3.5 shrink-0" />
              Est. {(trip.estimatedTotalCost ?? 0).toLocaleString()} {trip.currency}
              <span className="font-normal text-ink-400">
                {" "}(budget {(trip.budget ?? 0).toLocaleString()})
              </span>
            </span>
          </div>
        </div>

        <Button
          variant="outline"
          size="sm"
          isLoading={setSaved.isPending}
          onClick={() =>
            setSaved.mutate({ tripId: trip.id, isSaved: !trip.isSaved })
          }
          className="shrink-0 self-start"
        >
          {trip.isSaved ? (
            <BookmarkCheck className="h-4 w-4" />
          ) : (
            <Bookmark className="h-4 w-4" />
          )}
          {trip.isSaved ? "Saved" : "Save trip"}
        </Button>
      </div>

      {/* SCIF Intelligence Panel */}
      <ScifIntelligencePanel cognitiveTrace={trip.cognitiveTrace} />

      {/* Day tabs */}
      {numDays > 1 && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveDayIndex((i) => Math.max(0, i - 1))}
            disabled={activeDayIndex === 0}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-ink-100 bg-white text-ink-400 hover:bg-ink-50 disabled:opacity-30 dark:border-ink-700 dark:bg-ink-800 dark:hover:bg-ink-700"
            aria-label="Previous day"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <div className="flex flex-1 gap-1.5 overflow-x-auto pb-1">
            {days.map((day, idx) => (
              <button
                key={day.dayNumber}
                type="button"
                onClick={() => setActiveDayIndex(idx)}
                className={`shrink-0 rounded-xl px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap ${
                  idx === activeDayIndex
                    ? "bg-brand-600 text-white"
                    : "bg-white border border-ink-100 text-ink-600 hover:bg-ink-50 dark:border-ink-700 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700"
                }`}
              >
                Day {day.dayNumber}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() =>
              setActiveDayIndex((i) => Math.min(numDays - 1, i + 1))
            }
            disabled={activeDayIndex === numDays - 1}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-ink-100 bg-white text-ink-400 hover:bg-ink-50 disabled:opacity-30 dark:border-ink-700 dark:bg-ink-800 dark:hover:bg-ink-700"
            aria-label="Next day"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Active day activities */}
      {activeDay && (
        <div className="rounded-2xl border border-ink-100 bg-white dark:border-ink-700 dark:bg-ink-800 overflow-hidden">
          <div className="border-b border-ink-100 dark:border-ink-700 px-5 py-4">
            <h3 className="font-display text-lg font-semibold text-ink-900 dark:text-white">
              Day {activeDay.dayNumber}: {activeDay.title}
            </h3>
            <p className="text-xs text-ink-400 dark:text-ink-500 mt-0.5">
              {activeDay.activities.length} activit
              {activeDay.activities.length !== 1 ? "ies" : "y"} ·{" "}
              <span className="text-brand-500 dark:text-brand-400">
                Rate activities to teach SCIF your preferences
              </span>
            </p>
          </div>

          <div className="flex flex-col gap-3 p-4">
            {activeDay.activities.map((activity, i) => {
              const flatIdx = (dayActivityIndexMap[activeDayIndex] ?? 0) + i;
              const externalEnrichment = enrichedPlaces?.[flatIdx];
              return (
                <ActivityCard
                  key={`${activeDay.dayNumber}-${i}`}
                  activity={activity}
                  externalEnrichment={externalEnrichment}
                  isEnrichmentLoading={isEnriching}
                  currency={trip.currency}
                  destination={trip.destination}
                  feedbackState={getFeedbackState(activity.title)}
                  onFeedback={submitFeedback}
                  dayNumber={activeDay.dayNumber}
                  onGetAlternatives={handleGetAlternatives}
                  onRemove={handleRemove}
                  onMove={handleMove}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* Single-day fallback (shows all activities without tabs) */}
      {numDays === 1 && days[0] && (
        <div className="flex flex-col gap-3">
          {days[0].activities.map((activity, i) => {
            const externalEnrichment = enrichedPlaces?.[i];
            return (
              <ActivityCard
                key={i}
                activity={activity}
                externalEnrichment={externalEnrichment}
                isEnrichmentLoading={isEnriching}
                currency={trip.currency}
                destination={trip.destination}
                feedbackState={getFeedbackState(activity.title)}
                onFeedback={submitFeedback}
                dayNumber={days[0].dayNumber}
                onGetAlternatives={handleGetAlternatives}
                onRemove={handleRemove}
                onMove={handleMove}
              />
            );
          })}
        </div>
      )}

      {/* Editable Trip Components */}
      <PlannerChat tripId={trip.id} onModification={handleModification} />
      
      <AlternativePanel
        isOpen={alternativesActivity !== null}
        activityTitle={alternativesActivity?.activity.title ?? ""}
        alternatives={alternatives}
        isLoading={getAlternativesMutation.isPending}
        onReplace={handleReplace}
        onClose={() => setAlternativesActivity(null)}
      />
    </div>
  );
}
