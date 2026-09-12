"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  MapPin,
  Navigation2,
  Camera,
  Star,
  Clock as ClockIcon,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  ImageOff,
  Utensils,
  Landmark,
  TreePine,
  ShoppingBag,
  Wifi,
  Coffee,
  ChevronDown,
  ChevronUp,
  XCircle,
  Shield,
  Banknote,
  ThumbsUp,
  ThumbsDown,
  Brain,
} from "lucide-react";

import type { Activity } from "@/features/itinerary/domain/types";
import type { PlaceEnrichment } from "@/features/places/domain/types";
import type { FeedbackInput, FeedbackState } from "@/features/itinerary/hooks/useFeedback";
import type { RejectionReason } from "@/features/itinerary/data/feedbackApi";
import { Button } from "@/shared/components/ui/button";

// ─── Category icons ────────────────────────────────────────────────────────

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  food: Utensils,
  restaurant: Utensils,
  meal: Utensils,
  cafe: Coffee,
  coffee: Coffee,
  temple: Landmark,
  museum: Landmark,
  heritage: Landmark,
  culture: Landmark,
  historic: Landmark,
  park: TreePine,
  nature: TreePine,
  outdoor: TreePine,
  shopping: ShoppingBag,
  market: ShoppingBag,
  tech: Wifi,
};

function getCategoryIcon(category?: string | null): React.ElementType {
  if (!category) return Landmark;
  const lower = category.toLowerCase();
  for (const [key, Icon] of Object.entries(CATEGORY_ICONS)) {
    if (lower.includes(key)) return Icon;
  }
  return Landmark;
}

// ─── Rejection reasons ─────────────────────────────────────────────────────

const REJECTION_REASONS: { value: RejectionReason; label: string }[] = [
  { value: "too_expensive", label: "Too expensive" },
  { value: "too_crowded",   label: "Too crowded" },
  { value: "too_far",       label: "Too far" },
  { value: "not_interested", label: "Not interested" },
  { value: "already_visited", label: "Already visited" },
  { value: "wrong_type",    label: "Wrong type" },
  { value: "other",         label: "Other" },
];

// ─── Props ─────────────────────────────────────────────────────────────────

export interface ActivityCardProps {
  activity: Activity;
  /** Enrichment from the separate /places/enrich endpoint (may differ from inline) */
  externalEnrichment?: PlaceEnrichment;
  isEnrichmentLoading?: boolean;
  currency: string;
  destination: string;
  /**
   * Feedback state for this specific activity (from useFeedback hook in parent).
   * If undefined, feedback controls are not rendered (e.g., in saved/read-only views).
   */
  feedbackState?: FeedbackState;
  onFeedback?: (input: FeedbackInput) => void;
}

// ─── Main component ────────────────────────────────────────────────────────

export function ActivityCard({
  activity,
  externalEnrichment,
  isEnrichmentLoading = false,
  currency,
  destination,
  feedbackState,
  onFeedback,
}: ActivityCardProps) {
  const router = useRouter();
  const [showWhy, setShowWhy] = useState(false);
  const [showRejectMenu, setShowRejectMenu] = useState(false);

  // Prefer external enrichment, fall back to inline enrichment baked into the trip response.
  const inline = activity.placeEnrichment;
  const enr = externalEnrichment;

  const imageUrl = enr?.imageUrl ?? inline?.imageUrl ?? null;
  const matchedName = enr?.matchedPlaceName ?? inline?.matchedPlaceName ?? null;
  const address = enr?.address ?? inline?.address ?? null;
  const openingHours = enr?.openingHours ?? inline?.openingHours ?? null;
  const rating = enr?.rating ?? activity.rating ?? inline?.rating ?? null;
  const reviewsCount = enr?.reviewsCount ?? inline?.reviewsCount ?? null;
  const category = enr?.category ?? activity.category ?? inline?.category ?? null;
  const lat = enr?.lat ?? inline?.lat ?? null;
  const lon = enr?.lon ?? inline?.lon ?? null;
  const wikipediaSummary = enr?.wikipediaSummary ?? null;

  const isVerified = activity.verified === true;
  const isRejected = activity.scifRejected === true;
  const provider = activity.placeProvider ?? enr?.source ?? inline?.source ?? null;

  const CategoryIcon = getCategoryIcon(category);

  // Feedback state derived values
  const feedbackStatus = feedbackState?.status ?? "idle";
  const feedbackResult = feedbackState?.result ?? null;
  const userAccepted = feedbackStatus === "success" && feedbackResult !== null &&
    feedbackResult.message.includes("accept");
  const userRejected = feedbackStatus === "success" && feedbackResult !== null &&
    feedbackResult.message.includes("reject");

  const handleNavigate = () => {
    const dest = address ?? activity.location ?? matchedName ?? activity.title;
    if (lat != null && lon != null) {
      router.push(`/navigation?lat=${lat}&lon=${lon}&destination=${encodeURIComponent(dest)}`);
    } else {
      router.push(`/navigation?destination=${encodeURIComponent(dest)}`);
    }
  };

  const handleExploreAR = () => {
    router.push(`/explore?hint=${encodeURIComponent(activity.title)}`);
  };

  const handleAccept = () => {
    setShowRejectMenu(false);
    onFeedback?.({
      activityTitle: activity.title,
      activityCategory: activity.category ?? "other",
      eventType: "accept",
    });
  };

  const handleReject = (reason: RejectionReason) => {
    setShowRejectMenu(false);
    onFeedback?.({
      activityTitle: activity.title,
      activityCategory: activity.category ?? "other",
      eventType: "reject",
      rejectionReason: reason,
    });
  };

  const personalizationScore = activity.explanation?.personalizationScore;

  return (
    <div
      className={`overflow-hidden rounded-xl border transition-shadow hover:shadow-sm ${
        isRejected
          ? "border-red-100 bg-red-50/30 dark:border-red-900/30 dark:bg-red-950/10"
          : userRejected
          ? "border-orange-100 bg-orange-50/20 dark:border-orange-900/20 dark:bg-orange-950/10"
          : userAccepted
          ? "border-green-100 bg-green-50/20 dark:border-green-900/20 dark:bg-green-950/10"
          : "border-ink-100 bg-white dark:border-ink-700 dark:bg-ink-900"
      }`}
    >
      <div className="flex flex-col sm:flex-row">
        {/* Image / Category placeholder */}
        <div className="relative h-36 w-full shrink-0 bg-ink-100 dark:bg-ink-800 sm:h-auto sm:w-36">
          {imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl}
              alt={matchedName ?? activity.title}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-ink-300 dark:text-ink-600">
              {isEnrichmentLoading ? (
                <>
                  <div className="h-6 w-6 animate-pulse rounded-full bg-ink-200 dark:bg-ink-700" />
                  <span className="text-[10px]">Loading…</span>
                </>
              ) : (
                <>
                  <CategoryIcon className="h-6 w-6" />
                  <ImageOff className="h-3.5 w-3.5 opacity-50" />
                  <span className="text-[10px] text-center leading-tight">
                    Photo unavailable
                  </span>
                </>
              )}
            </div>
          )}

          {/* SCIF Rejected overlay */}
          {isRejected && (
            <div className="absolute inset-0 flex items-center justify-center bg-red-900/60 backdrop-blur-[1px]">
              <XCircle className="h-8 w-8 text-white" />
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex flex-1 flex-col gap-2 p-4">
          {/* Time + title row */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1.5 text-xs font-medium text-ink-400 dark:text-ink-500">
                <ClockIcon className="h-3 w-3 shrink-0" />
                {activity.time}
                {activity.mealType && (
                  <>
                    <span className="text-ink-200 dark:text-ink-700">·</span>
                    <Utensils className="h-3 w-3 shrink-0 text-amber-500" />
                    <span className="capitalize text-amber-600 dark:text-amber-400">
                      {activity.mealType}
                    </span>
                  </>
                )}
              </p>

              <p className="mt-0.5 font-medium text-ink-900 dark:text-white leading-tight">
                {matchedName ?? activity.title}
              </p>

              {/* Show Qwen-generated title if different from verified name */}
              {matchedName && matchedName !== activity.title && (
                <p className="text-xs text-ink-400 dark:text-ink-500">
                  AI intent: {activity.slotIntent ?? activity.title}
                </p>
              )}
            </div>

            {/* Rating badge */}
            {rating != null && (
              <span className="flex shrink-0 items-center gap-1 rounded-lg bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                <Star className="h-3 w-3 fill-current" />
                {rating.toFixed(1)}
                {reviewsCount != null && (
                  <span className="font-normal opacity-70">
                    ({reviewsCount.toLocaleString()})
                  </span>
                )}
              </span>
            )}
          </div>

          {/* Description */}
          <p className="text-sm text-ink-500 dark:text-ink-400 leading-relaxed">
            {activity.description}
          </p>

          {/* Wikipedia summary if available */}
          {wikipediaSummary && (
            <p className="text-xs text-ink-400 dark:text-ink-500 italic border-l-2 border-ink-200 dark:border-ink-700 pl-2">
              {wikipediaSummary.length > 200
                ? `${wikipediaSummary.slice(0, 200)}…`
                : wikipediaSummary}
            </p>
          )}

          {/* Metadata badges row */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400 dark:text-ink-500">
            {/* Verified badge */}
            {isVerified && (
              <span className="flex items-center gap-1 font-medium text-green-600 dark:text-green-400">
                <CheckCircle2 className="h-3 w-3" />
                Verified
                {provider && (
                  <span className="font-normal opacity-70">({provider})</span>
                )}
              </span>
            )}
            {!isVerified && enr !== undefined && (
              <span className="flex items-center gap-1 text-amber-500 dark:text-amber-400">
                <AlertTriangle className="h-3 w-3" />
                Unverified
              </span>
            )}

            {/* Category */}
            {category && (
              <span className="rounded-md bg-ink-50 px-2 py-0.5 font-medium text-ink-600 dark:bg-ink-800 dark:text-ink-300">
                {category}
              </span>
            )}

            {/* Address */}
            {(address ?? activity.location) && (
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3 shrink-0" />
                {address ?? activity.location}
              </span>
            )}

            {/* Personalization badge — only when score is meaningfully non-neutral */}
            {personalizationScore != null && Math.abs(personalizationScore - 0.5) > 0.1 && (
              <span
                className={`flex items-center gap-1 rounded-md px-2 py-0.5 font-medium ${
                  personalizationScore >= 0.65
                    ? "bg-brand-50 text-brand-600 dark:bg-brand-900/20 dark:text-brand-400"
                    : "bg-ink-50 text-ink-400 dark:bg-ink-800 dark:text-ink-500"
                }`}
                title={`Personalization score: ${Math.round(personalizationScore * 100)}%`}
              >
                <Brain className="h-3 w-3 shrink-0" />
                {personalizationScore >= 0.65 ? "Personalized for you" : "Low match"}
              </span>
            )}
          </div>

          {/* Opening hours + cost row */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400 dark:text-ink-500">
            {openingHours ? (
              <span className="flex items-center gap-1">
                <ClockIcon className="h-3 w-3 shrink-0" />
                {openingHours}
              </span>
            ) : (
              <span className="text-ink-300 dark:text-ink-600">Hours: unavailable</span>
            )}
            <span className="flex items-center gap-1">
              <Banknote className="h-3 w-3 shrink-0" />
              AI est. {activity.estimatedCost.toLocaleString()} {currency}
            </span>
          </div>

          {/* SCIF rejection banner */}
          {isRejected && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-400">
              <Shield className="h-3.5 w-3.5 mt-0.5 shrink-0" />
              <span>
                <strong>SCIF removed:</strong>{" "}
                {activity.scifRejectionReason ?? "Rejected by cognitive evaluation"}
              </span>
            </div>
          )}

          {/* User feedback confirmation banners */}
          {userAccepted && (
            <div className="flex items-center gap-2 rounded-lg bg-green-50 px-3 py-1.5 text-xs text-green-700 dark:bg-green-900/20 dark:text-green-400">
              <ThumbsUp className="h-3.5 w-3.5 shrink-0" />
              <span>
                Feedback saved — your preferences have been updated.
                {feedbackResult?.new_inferred_preferences &&
                  feedbackResult.new_inferred_preferences.length > 0 && (
                    <span className="block mt-0.5 opacity-80">
                      New insight: "{feedbackResult.new_inferred_preferences[0]}"
                    </span>
                  )}
              </span>
            </div>
          )}
          {userRejected && (
            <div className="flex items-center gap-2 rounded-lg bg-orange-50 px-3 py-1.5 text-xs text-orange-700 dark:bg-orange-900/20 dark:text-orange-400">
              <ThumbsDown className="h-3.5 w-3.5 shrink-0" />
              <span>Noted — similar activities will be ranked lower in future trips.</span>
            </div>
          )}
          {feedbackState?.status === "error" && (
            <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-400">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>{feedbackState.error ?? "Could not save feedback."}</span>
            </div>
          )}

          {/* Action buttons row */}
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleNavigate}
              className="flex items-center gap-1.5"
              aria-label={`Navigate to ${activity.title}`}
            >
              <Navigation2 className="h-3.5 w-3.5" />
              Navigate
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleExploreAR}
              className="flex items-center gap-1.5"
              aria-label={`Explore ${activity.title} in AR`}
            >
              <Camera className="h-3.5 w-3.5" />
              Explore in AR
            </Button>

            {/* Feedback buttons — only shown when onFeedback is wired in */}
            {onFeedback && feedbackStatus === "idle" && !isRejected && (
              <div className="relative ml-auto flex items-center gap-1">
                {/* Accept */}
                <button
                  type="button"
                  onClick={handleAccept}
                  className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium
                    text-green-700 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-900/20
                    transition-colors border border-green-200 dark:border-green-800"
                  aria-label={`Like ${activity.title}`}
                  title="Looks good — teach SCIF what you enjoy"
                >
                  <ThumbsUp className="h-3.5 w-3.5" />
                  Like
                </button>

                {/* Reject toggle — opens reason menu */}
                <button
                  type="button"
                  onClick={() => setShowRejectMenu((v) => !v)}
                  className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium
                    text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20
                    transition-colors border border-red-200 dark:border-red-800"
                  aria-label={`Dislike ${activity.title}`}
                  aria-expanded={showRejectMenu}
                  title="Not a match — tell SCIF why"
                >
                  <ThumbsDown className="h-3.5 w-3.5" />
                  Dislike
                </button>

                {/* Rejection reason popover */}
                {showRejectMenu && (
                  <div
                    className="absolute bottom-full right-0 mb-1 z-20 min-w-[160px]
                      rounded-xl border border-ink-200 bg-white shadow-lg p-2 flex flex-col gap-0.5
                      dark:border-ink-700 dark:bg-ink-900"
                    role="menu"
                    aria-label="Rejection reason"
                  >
                    <p className="px-2 py-1 text-[10px] font-semibold text-ink-500 dark:text-ink-400 uppercase tracking-wide">
                      Why not?
                    </p>
                    {REJECTION_REASONS.map((r) => (
                      <button
                        key={r.value}
                        type="button"
                        role="menuitem"
                        onClick={() => handleReject(r.value)}
                        className="rounded-lg px-3 py-1.5 text-left text-xs text-ink-700
                          hover:bg-red-50 hover:text-red-700 dark:text-ink-300
                          dark:hover:bg-red-900/20 dark:hover:text-red-400 transition-colors"
                      >
                        {r.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Feedback pending spinner */}
            {feedbackStatus === "pending" && (
              <div className="ml-auto flex items-center gap-1.5 text-xs text-ink-400 dark:text-ink-500">
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-300 border-t-brand-500" />
                Saving…
              </div>
            )}

            {/* Why this? */}
            {activity.explanation && (
              <button
                type="button"
                onClick={() => setShowWhy((v) => !v)}
                className={`flex items-center gap-1 text-xs text-brand-600 hover:underline dark:text-brand-400 ${
                  onFeedback ? "" : "ml-auto"
                }`}
                aria-expanded={showWhy}
                aria-label="Why was this activity selected?"
              >
                <Sparkles className="h-3 w-3" />
                Why this?
                {showWhy ? (
                  <ChevronUp className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
              </button>
            )}
          </div>

          {/* Why this panel */}
          {showWhy && activity.explanation && (
            <div className="mt-1 rounded-xl border border-ink-100 bg-ink-50 p-3 text-xs dark:border-ink-700 dark:bg-ink-900">
              <p className="font-medium text-ink-800 dark:text-white mb-2">
                Why this was selected
              </p>
              <p className="text-ink-600 dark:text-ink-400 leading-relaxed">
                {activity.explanation.reasonText}
              </p>

              {/* Score pills */}
              <div className="mt-2 flex flex-wrap gap-2">
                {activity.explanation.budgetMatch > 0 && (
                  <MatchPill label="Budget" value={activity.explanation.budgetMatch} />
                )}
                {activity.explanation.interestMatch > 0 && (
                  <MatchPill label="Interests" value={activity.explanation.interestMatch} />
                )}
                {activity.explanation.weatherMatch > 0 && (
                  <MatchPill label="Weather" value={activity.explanation.weatherMatch} />
                )}
                {activity.explanation.contextScore > 0 && (
                  <MatchPill label="Context" value={activity.explanation.contextScore} />
                )}
                {activity.explanation.personalizationScore != null &&
                  activity.explanation.personalizationScore > 0 && (
                    <MatchPill
                      label="Personalization"
                      value={activity.explanation.personalizationScore}
                      icon={<Brain className="h-2.5 w-2.5" />}
                    />
                  )}
              </div>

              {activity.explanation.confidence > 0 && (
                <p className="mt-2 text-ink-400 dark:text-ink-500">
                  Confidence:{" "}
                  <strong className="text-ink-700 dark:text-ink-300">
                    {qualitativeConfidence(activity.explanation.confidence)}
                  </strong>
                </p>
              )}

              {/* Unavailable factors disclaimer */}
              {activity.explanation.unavailableFactors.length > 0 && (
                <p className="mt-1.5 text-ink-400 dark:text-ink-500 italic">
                  Note: some signals unavailable during planning (
                  {activity.explanation.unavailableFactors.join(", ")})
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────────────────

function qualitativeConfidence(score: number): string {
  if (score >= 0.8) return "High";
  if (score >= 0.5) return "Medium";
  return "Low";
}

function qualitativeMatch(score: number): string {
  if (score >= 0.7) return "Strong";
  if (score >= 0.4) return "Good";
  return "Partial";
}

function matchColor(score: number): string {
  if (score >= 0.7)
    return "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400";
  if (score >= 0.4)
    return "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400";
  return "bg-ink-50 text-ink-600 dark:bg-ink-800 dark:text-ink-400";
}

function MatchPill({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon?: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-semibold ${matchColor(value)}`}
    >
      {icon}
      {label}: {qualitativeMatch(value)}
    </span>
  );
}
