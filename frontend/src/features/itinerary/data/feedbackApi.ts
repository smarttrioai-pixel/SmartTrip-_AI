/**
 * Activity feedback API client for SmartTrip AI.
 *
 * Calls POST /api/v1/memory/feedback — the adaptive learning endpoint.
 * Every call updates behavioral feature_weights in Firestore
 * (memory_behavioral/{uid}) and persists a feedback document, which
 * influence future trip recommendations.
 */
import { apiClient } from "@/core/api/apiClient";


export type FeedbackEventType = "accept" | "reject" | "edit";

export type RejectionReason =
  | "too_expensive"
  | "too_crowded"
  | "too_far"
  | "not_interested"
  | "already_visited"
  | "wrong_type"
  | "other";

export interface ActivityFeedbackPayload {
  trip_id: string;
  activity_title: string;
  activity_category: string;
  event_type: FeedbackEventType;
  rejection_reason?: RejectionReason | null;
  rating?: number | null;
  free_text?: string | null;
}

export interface ActivityFeedbackResult {
  message: string;
  feature_deltas_applied: Record<string, number>;
  updated_feature_weights: Record<string, number>;
  new_inferred_preferences: string[];
}

export async function recordActivityFeedback(
  payload: ActivityFeedbackPayload
): Promise<ActivityFeedbackResult> {
  const { data } = await apiClient.post<ActivityFeedbackResult>(
    "/memory/feedback",
    payload
  );
  return data;
}

