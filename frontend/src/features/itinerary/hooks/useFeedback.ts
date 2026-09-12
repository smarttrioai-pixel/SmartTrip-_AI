/**
 * useFeedback — React hook for per-activity user feedback.
 *
 * Provides a mutation that calls POST /memory/feedback.
 * Uses optimistic UI: the button state updates immediately and
 * the server call happens in the background. On error, the state
 * is rolled back and an error indicator is shown.
 *
 * Usage:
 *   const { submitFeedback, feedbackState, isPending } = useFeedback(tripId);
 *   submitFeedback({ activityTitle, activityCategory, eventType, rejectionReason });
 */
"use client";

import { useState, useCallback } from "react";
import {
  recordActivityFeedback,
  type FeedbackEventType,
  type RejectionReason,
  type ActivityFeedbackResult,
} from "@/features/itinerary/data/feedbackApi";

export interface FeedbackInput {
  activityTitle: string;
  activityCategory: string;
  eventType: FeedbackEventType;
  rejectionReason?: RejectionReason | null;
  rating?: number | null;
  freeText?: string | null;
}

export type FeedbackStatus = "idle" | "pending" | "success" | "error";

export interface FeedbackState {
  status: FeedbackStatus;
  result: ActivityFeedbackResult | null;
  error: string | null;
}

/**
 * Per-activity feedback hook.
 *
 * @param tripId  The trip ID this activity belongs to.
 */
export function useFeedback(tripId: string) {
  // Map from activity title → feedback state so each activity card
  // has independent state within the same trip view.
  const [stateMap, setStateMap] = useState<Record<string, FeedbackState>>({});

  const getFeedbackState = useCallback(
    (activityTitle: string): FeedbackState => {
      return (
        stateMap[activityTitle] ?? { status: "idle", result: null, error: null }
      );
    },
    [stateMap]
  );

  const submitFeedback = useCallback(
    async (input: FeedbackInput) => {
      const key = input.activityTitle;

      // Optimistic: mark as pending immediately
      setStateMap((prev) => ({
        ...prev,
        [key]: { status: "pending", result: null, error: null },
      }));

      try {
        const result = await recordActivityFeedback({
          trip_id: tripId,
          activity_title: input.activityTitle,
          activity_category: input.activityCategory,
          event_type: input.eventType,
          rejection_reason: input.rejectionReason ?? null,
          rating: input.rating ?? null,
          free_text: input.freeText ?? null,
        });

        setStateMap((prev) => ({
          ...prev,
          [key]: { status: "success", result, error: null },
        }));
      } catch {
        setStateMap((prev) => ({
          ...prev,
          [key]: {
            status: "error",
            result: null,
            error: "Could not save feedback. Please try again.",
          },
        }));
        // Auto-reset error state after 3 seconds so the user can retry
        setTimeout(() => {
          setStateMap((prev) => ({
            ...prev,
            [key]: { status: "idle", result: null, error: null },
          }));
        }, 3000);
      }
    },
    [tripId]
  );

  return { submitFeedback, getFeedbackState };
}
