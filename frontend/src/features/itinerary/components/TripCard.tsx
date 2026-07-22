import { Bookmark, Calendar } from "lucide-react";

import type { Trip } from "@/features/itinerary/domain/types";

export function TripCard({ trip }: { trip: Trip }) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-ink-100 bg-white p-5 shadow-card dark:border-ink-700 dark:bg-ink-800">
      <div className="flex items-start justify-between">
        <p className="font-medium text-ink-900 dark:text-white">{trip.destination}</p>
        {trip.isSaved && <Bookmark className="h-4 w-4 shrink-0 fill-brand-500 text-brand-500" />}
      </div>
      <p className="flex items-center gap-1.5 text-xs text-ink-400">
        <Calendar className="h-3.5 w-3.5" />
        {trip.startDate} — {trip.endDate}
      </p>
      <p className="text-sm font-medium text-brand-600">
        {(trip.estimatedTotalCost ?? 0).toLocaleString()} {trip.currency}
      </p>
    </div>
  );
}
