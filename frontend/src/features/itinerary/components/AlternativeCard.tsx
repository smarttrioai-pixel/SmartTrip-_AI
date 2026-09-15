import { MapPin, Star, DollarSign, Clock, ArrowRightCircle } from "lucide-react";
import type { ActivityAlternative } from "@/features/itinerary/domain/types";
import { Button } from "@/shared/components/ui/button";

export interface AlternativeCardProps {
  alternative: ActivityAlternative;
  onReplace: () => void;
}

export function AlternativeCard({ alternative, onReplace }: AlternativeCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-ink-200 bg-white p-4 shadow-sm transition-hover hover:border-brand-300 dark:border-ink-700 dark:bg-ink-800">
      <div className="flex justify-between items-start gap-2">
        <h4 className="font-medium text-ink-900 dark:text-white leading-tight">
          {alternative.title}
        </h4>
        <span className="shrink-0 rounded bg-ink-100 px-2 py-0.5 text-xs font-medium text-ink-600 dark:bg-ink-700 dark:text-ink-300">
          {alternative.category}
        </span>
      </div>

      <p className="text-sm text-ink-600 dark:text-ink-400">
        {alternative.description}
      </p>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-500 dark:text-ink-400">
        {alternative.rating != null && (
          <span className="flex items-center gap-1 font-medium text-amber-600 dark:text-amber-500">
            <Star className="h-3.5 w-3.5 fill-current" />
            {alternative.rating.toFixed(1)}
          </span>
        )}
        <span className="flex items-center gap-1">
          <DollarSign className="h-3.5 w-3.5" />
          Est. {alternative.estimated_cost}
        </span>
        {alternative.distance_meters != null && (
          <span className="flex items-center gap-1">
            <MapPin className="h-3.5 w-3.5" />
            {Math.round(alternative.distance_meters)}m away
          </span>
        )}
        {alternative.duration_minutes != null && (
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {alternative.duration_minutes} min
          </span>
        )}
      </div>

      <div className="mt-1 rounded-lg bg-brand-50 p-3 text-xs italic text-brand-700 dark:bg-brand-900/20 dark:text-brand-300">
        "{alternative.reason}"
      </div>

      <Button
        onClick={onReplace}
        className="mt-2 w-full flex items-center justify-center gap-2"
      >
        <ArrowRightCircle className="h-4 w-4" />
        Replace with this
      </Button>
    </div>
  );
}
