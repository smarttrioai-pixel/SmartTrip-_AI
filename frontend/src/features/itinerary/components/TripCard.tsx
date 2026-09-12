import { Bookmark, Calendar, Wallet, MapPin, Brain, CloudSun } from "lucide-react";
import type { Trip } from "@/features/itinerary/domain/types";

export function TripCard({ trip }: { trip: Trip }) {
  const numDays = trip.days?.length ?? 0;
  const hasScif = trip.cognitiveTrace != null;
  const pipeline = trip.cognitiveTrace?.scif_pipeline;
  const agentCount = pipeline?.agent_outputs?.length ?? 0;

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-ink-100 bg-white p-5 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-md dark:border-ink-700 dark:bg-ink-800">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-brand-500" />
          <p className="font-medium text-ink-900 dark:text-white truncate">
            {trip.destination}
          </p>
        </div>
        {trip.isSaved && (
          <Bookmark className="h-4 w-4 shrink-0 fill-brand-500 text-brand-500" />
        )}
      </div>

      {/* Dates + style */}
      <div className="flex items-center gap-3 text-xs text-ink-400 dark:text-ink-500">
        <span className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5 shrink-0" />
          {trip.startDate} — {trip.endDate}
        </span>
        <span className="text-ink-200 dark:text-ink-700">·</span>
        <span className="capitalize">{trip.travelStyle}</span>
      </div>

      {/* Cost */}
      <p className="flex items-center gap-1 text-sm font-medium text-brand-600 dark:text-brand-400">
        <Wallet className="h-3.5 w-3.5 shrink-0" />
        {(trip.estimatedTotalCost ?? 0).toLocaleString()} {trip.currency}
        <span className="ml-1 font-normal text-ink-400 dark:text-ink-500 text-xs">
          / {numDays} day{numDays !== 1 ? "s" : ""}
        </span>
      </p>

      {/* SCIF badge */}
      <div className="flex flex-wrap gap-1.5">
        {hasScif && (
          <span className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-2 py-0.5 text-[10px] font-semibold text-brand-600 dark:bg-brand-900/30 dark:text-brand-400">
            <Brain className="h-2.5 w-2.5" />
            SCIF
            {agentCount > 0 && ` · ${agentCount} agents`}
          </span>
        )}
        {pipeline?.weather && (
          <span className="inline-flex items-center gap-1 rounded-md bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-600 dark:bg-sky-900/30 dark:text-sky-400">
            <CloudSun className="h-2.5 w-2.5" />
            Weather
          </span>
        )}
      </div>
    </div>
  );
}
