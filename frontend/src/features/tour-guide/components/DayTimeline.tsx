"use client";

import { CheckCircle2, Clock, ImageOff } from "lucide-react";

import type { Trip } from "@/features/itinerary/domain/types";
import { cn } from "@/shared/lib/utils";

interface DayTimelineProps {
  trip: Trip;
  dayNumber: number;
  activeActivityIndex: number | null;
  onSelectActivity: (index: number) => void;
  expanded?: boolean;
}

export function DayTimeline({
  trip,
  dayNumber,
  activeActivityIndex,
  onSelectActivity,
  expanded = false,
}: DayTimelineProps) {
  const day = trip.days.find((d) => d.dayNumber === dayNumber) ?? trip.days[0];
  if (!day) return null;

  const activities = expanded ? day.activities : day.activities;

  const weatherConstraints =
    trip.cognitiveTrace?.scif_pipeline?.weather_constraints ?? [];
  const smartAdjustment = weatherConstraints.find((c) =>
    c.toLowerCase().includes("rain") || c.toLowerCase().includes("outdoor")
  );

  return (
    <div className="rounded-2xl border border-ink-100 bg-white dark:border-ink-700 dark:bg-ink-900 overflow-hidden">
      <div className="px-4 py-3 border-b border-ink-100 dark:border-ink-800">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-400">Today</p>
        <h2 className="font-display text-base font-semibold text-ink-900 dark:text-white">
          {day.title || `Day ${day.dayNumber}`}
        </h2>
        <p className="text-xs text-ink-400 mt-0.5">
          {trip.destination} · {activities.length} activities
        </p>
      </div>

      {smartAdjustment && (
        <div className="mx-4 mt-3 rounded-xl bg-amber-50 border border-amber-100 px-3 py-2 dark:bg-amber-950/20 dark:border-amber-900/30">
          <p className="text-[11px] font-semibold text-amber-700 dark:text-amber-400">Smart adjustment</p>
          <p className="text-xs text-amber-800 dark:text-amber-300 mt-0.5">{smartAdjustment}</p>
        </div>
      )}

      <div className="p-4 flex flex-col gap-2 max-h-[480px] overflow-y-auto">
        {activities.map((activity, idx) => {
          const isActive = activeActivityIndex === idx;
          const imageUrl = activity.placeEnrichment?.imageUrl;

          return (
            <button
              key={`${activity.time}-${activity.title}-${idx}`}
              type="button"
              onClick={() => onSelectActivity(idx)}
              className={cn(
                "flex items-start gap-3 rounded-xl border p-3 text-left transition-colors w-full",
                isActive
                  ? "border-brand-300 bg-brand-50 dark:border-brand-700 dark:bg-brand-900/20"
                  : "border-ink-100 hover:bg-ink-50 dark:border-ink-800 dark:hover:bg-ink-800/50"
              )}
            >
              <div className="shrink-0 text-center w-14">
                <p className="text-[10px] font-semibold text-ink-400 flex items-center gap-0.5 justify-center">
                  <Clock className="h-3 w-3" />
                  {activity.time}
                </p>
              </div>

              <div className="relative h-12 w-12 shrink-0 rounded-lg overflow-hidden bg-ink-100 dark:bg-ink-800">
                {imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={imageUrl} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-ink-300">
                    <ImageOff className="h-4 w-4" />
                  </div>
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-ink-900 dark:text-white truncate">
                    {activity.title}
                  </p>
                  {activity.verified && (
                    <span className="shrink-0 flex items-center gap-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      Verified
                    </span>
                  )}
                </div>
                {activity.category && (
                  <p className="text-[11px] text-ink-400 capitalize mt-0.5">{activity.category}</p>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
