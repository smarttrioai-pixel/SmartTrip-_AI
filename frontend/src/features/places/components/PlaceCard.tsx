"use client";

import { useRouter } from "next/navigation";
import { Camera, ImageOff, MapPin, Navigation2, Star, Clock as ClockIcon, Sparkles } from "lucide-react";

import type { PlaceEnrichment } from "@/features/places/domain/types";
import type { Explanation } from "@/features/itinerary/domain/types";
import { Button } from "@/shared/components/ui/button";

export interface PlaceCardProps {
  title: string;
  time: string;
  description: string;
  location: string;
  aiEstimatedCost: number;
  currency: string;
  enrichment: PlaceEnrichment | undefined;
  isEnrichmentLoading: boolean;
  explanation?: Explanation | null;
}

export function PlaceCard({
  title,
  time,
  description,
  location,
  aiEstimatedCost,
  currency,
  enrichment,
  isEnrichmentLoading,
  explanation,
}: PlaceCardProps) {
  const router = useRouter();

  const handleNavigate = () => {
    const dest = enrichment?.address ?? location ?? title;
    router.push(`/navigation?destination=${encodeURIComponent(dest)}`);
  };

  const handleExploreAR = () => {
    router.push(`/explore?hint=${encodeURIComponent(title)}`);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-ink-100 bg-white dark:border-ink-700 dark:bg-ink-900">
      <div className="flex flex-col sm:flex-row">
        <div className="relative h-40 w-full shrink-0 bg-ink-100 dark:bg-ink-800 sm:h-auto sm:w-40">
          {enrichment?.imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={enrichment.imageUrl} alt={enrichment.matchedPlaceName ?? title} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-ink-300 dark:text-ink-600">
              <ImageOff className="h-6 w-6" />
              <span className="text-[10px]">{isEnrichmentLoading ? "Loading…" : "No image available"}</span>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-2 p-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-medium text-ink-400">
                <ClockIcon className="h-3 w-3" /> {time}
              </p>
              <p className="font-medium text-ink-900 dark:text-white">{title}</p>
            </div>
            {enrichment?.rating != null && (
              <span className="flex shrink-0 items-center gap-1 rounded-lg bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                <Star className="h-3 w-3 fill-current" /> {enrichment.rating}
                {enrichment.ratingScale && <span className="font-normal opacity-70">/7</span>}
              </span>
            )}
          </div>

          <p className="text-sm text-ink-400">{description}</p>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400">
            {enrichment?.category && (
              <span className="rounded-md bg-ink-50 px-2 py-0.5 font-medium text-ink-600 dark:bg-ink-800 dark:text-ink-300">
                {enrichment.category}
              </span>
            )}
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3" /> {enrichment?.address ?? location}
            </span>
            {enrichment?.reviewsCount != null ? (
              <span>{enrichment.reviewsCount} reviews</span>
            ) : (
              enrichment && <span title={enrichment.reviewsCountNote ?? undefined}>Reviews: not available</span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400">
            <span title={enrichment?.openingHoursNote ?? undefined}>
              Hours: {enrichment?.openingHours ?? "not available"}
            </span>
            <span>
              AI-estimated cost: ~{aiEstimatedCost.toLocaleString()} {currency}
            </span>
            {enrichment?.lat != null && enrichment?.lon != null && (
              <span className="font-mono">
                {enrichment.lat.toFixed(4)}, {enrichment.lon.toFixed(4)}
              </span>
            )}
          </div>

          <div className="mt-1 flex gap-2">
            <Button size="sm" variant="outline" onClick={handleNavigate} className="flex items-center gap-1.5">
              <Navigation2 className="h-3.5 w-3.5" /> Navigate
            </Button>
            <Button size="sm" variant="outline" onClick={handleExploreAR} className="flex items-center gap-1.5">
              <Camera className="h-3.5 w-3.5" /> Explore in AR
            </Button>
          </div>

          {explanation && (
            <details className="mt-1 text-xs">
              <summary className="flex w-fit cursor-pointer items-center gap-1 text-brand-600 hover:underline">
                <Sparkles className="h-3 w-3" /> Why this?
              </summary>
              <div className="mt-1.5 rounded-lg bg-ink-50 p-2.5 text-ink-700 dark:bg-ink-900 dark:text-ink-100">
                <p>{explanation.reasonText}</p>
                <p className="mt-1 text-ink-400">Confidence: {Math.round(explanation.confidence * 100)}%</p>
              </div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
