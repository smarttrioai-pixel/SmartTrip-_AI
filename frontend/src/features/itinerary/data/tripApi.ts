import { apiClient } from "@/core/api/apiClient";
import type {
  GenerateItineraryPayload,
  Trip,
  PlaceEnrichmentInline,
  ModifyItineraryRequest,
  ModifyItineraryResponse,
  AlternativesResponse,
  ReplaceActivityRequest,
  MoveActivityRequest,
  ReorderRequest,
} from "@/features/itinerary/domain/types";
import type { CognitiveTrace } from "@/features/itinerary/domain/scif-types";

// ─── Wire-format DTOs (snake_case, exactly as backend sends) ────────────────

interface ExplanationDto {
  reason_text: string;
  budget_match: number;
  interest_match: number;
  weather_match?: number;
  context_score: number;
  confidence: number;
  unavailable_factors?: string[];
}

interface PlaceEnrichmentDto {
  found: boolean;
  matched_place_name?: string | null;
  image_url?: string | null;
  rating?: number | null;
  rating_scale?: string | null;
  reviews_count?: number | null;
  address?: string | null;
  opening_hours?: string | null;
  lat?: number | null;
  lon?: number | null;
  category?: string | null;
  source?: string | null;
  source_id?: string | null;
}

interface ActivityDto {
  time: string;
  title: string;
  description: string;
  location: string;
  estimated_cost: number;
  category?: string | null;
  reason?: string | null;
  meal_type?: string | null;
  food_query?: string | null;
  explanation: ExplanationDto | null;
  place_enrichment?: PlaceEnrichmentDto | null;
  scif_rejected?: boolean | null;
  scif_rejection_reason?: string | null;
  verified?: boolean | null;
  place_provider?: string | null;
  place_id?: string | null;
  rating?: number | null;
  user_ratings_total?: number | null;
  slot_intent?: string | null;
}

interface DayPlanDto {
  day_number: number;
  title: string;
  activities: ActivityDto[];
}

interface TripDto {
  id: string;
  destination: string;
  start_date: string;
  end_date: string;
  budget: number;
  currency: string;
  travel_style: string;
  days: DayPlanDto[];
  estimated_total_cost: number;
  is_saved: boolean;
  cognitive_trace?: CognitiveTrace | null;
}

// ─── Mapping helpers ─────────────────────────────────────────────────────────

function toPlaceEnrichment(dto: PlaceEnrichmentDto): PlaceEnrichmentInline {
  return {
    found: dto.found,
    matchedPlaceName: dto.matched_place_name,
    imageUrl: dto.image_url,
    rating: dto.rating,
    ratingScale: dto.rating_scale,
    reviewsCount: dto.reviews_count,
    address: dto.address,
    openingHours: dto.opening_hours,
    lat: dto.lat,
    lon: dto.lon,
    category: dto.category,
    source: dto.source,
    sourceId: dto.source_id,
  };
}

function toTrip(dto: TripDto): Trip {
  return {
    id: dto.id,
    destination: dto.destination,
    startDate: dto.start_date,
    endDate: dto.end_date,
    budget: dto.budget,
    currency: dto.currency,
    travelStyle: dto.travel_style,
    estimatedTotalCost: dto.estimated_total_cost,
    isSaved: dto.is_saved,
    cognitiveTrace: dto.cognitive_trace ?? null,
    days: dto.days.map((day) => ({
      dayNumber: day.day_number,
      title: day.title,
      activities: day.activities.map((a) => ({
        time: a.time,
        title: a.title,
        description: a.description,
        location: a.location,
        estimatedCost: a.estimated_cost,
        category: a.category,
        reason: a.reason,
        mealType: a.meal_type,
        foodQuery: a.food_query,
        explanation: a.explanation
          ? {
              reasonText: a.explanation.reason_text,
              budgetMatch: a.explanation.budget_match,
              interestMatch: a.explanation.interest_match,
              weatherMatch: a.explanation.weather_match ?? 0,
              contextScore: a.explanation.context_score,
              confidence: a.explanation.confidence,
              unavailableFactors: a.explanation.unavailable_factors ?? [],
            }
          : null,
        placeEnrichment: a.place_enrichment
          ? toPlaceEnrichment(a.place_enrichment)
          : null,
        scifRejected: a.scif_rejected,
        scifRejectionReason: a.scif_rejection_reason,
        verified: a.verified,
        placeProvider: a.place_provider,
        placeId: a.place_id,
        rating: a.rating,
        userRatingsTotal: a.user_ratings_total,
        slotIntent: a.slot_intent,
      })),
    })),
  };
}

// ─── API surface ──────────────────────────────────────────────────────────────

export const tripApi = {
  async generate(payload: GenerateItineraryPayload): Promise<Trip> {
    const { data } = await apiClient.post<TripDto>("/trips/generate", {
      destination: payload.destination,
      start_date: payload.startDate,
      end_date: payload.endDate,
      budget: payload.budget,
      currency: payload.currency,
      travel_style: payload.travelStyle,
      interests: payload.interests,
      transport: payload.transport,
    });
    return toTrip(data);
  },

  async list(savedOnly = false): Promise<Trip[]> {
    const { data } = await apiClient.get<TripDto[]>("/trips", {
      params: { saved_only: savedOnly },
    });
    return data.map(toTrip);
  },

  async setSaved(tripId: string, isSaved: boolean): Promise<void> {
    await apiClient.patch(`/trips/${tripId}/save`, { is_saved: isSaved });
  },

  async remove(tripId: string): Promise<void> {
    await apiClient.delete(`/trips/${tripId}`);
  },

  async modifyItinerary(
    tripId: string,
    payload: ModifyItineraryRequest
  ): Promise<ModifyItineraryResponse> {
    const { data } = await apiClient.post<ModifyItineraryResponse>(`/trips/${tripId}/modify`, payload);
    return data;
  },

  async getAlternatives(
    tripId: string,
    activityId: string,
    dayNumber: number
  ): Promise<AlternativesResponse> {
    const { data } = await apiClient.get<AlternativesResponse>(
      `/trips/${tripId}/activities/${activityId}/alternatives`,
      { params: { day_number: dayNumber } }
    );
    return data;
  },

  async replaceActivity(
    tripId: string,
    activityId: string,
    payload: ReplaceActivityRequest
  ): Promise<ModifyItineraryResponse> {
    const { data } = await apiClient.post<ModifyItineraryResponse>(
      `/trips/${tripId}/activities/${activityId}/replace`,
      payload
    );
    return data;
  },

  async moveActivity(
    tripId: string,
    activityId: string,
    payload: MoveActivityRequest
  ): Promise<ModifyItineraryResponse> {
    const { data } = await apiClient.post<ModifyItineraryResponse>(
      `/trips/${tripId}/activities/${activityId}/move`,
      payload
    );
    return data;
  },

  async removeActivity(
    tripId: string,
    activityId: string,
    dayNumber: number
  ): Promise<ModifyItineraryResponse> {
    const { data } = await apiClient.delete<ModifyItineraryResponse>(
      `/trips/${tripId}/activities/${activityId}`,
      { data: { day_number: dayNumber } }
    );
    return data;
  },

  async reorderActivities(
    tripId: string,
    payload: ReorderRequest
  ): Promise<ModifyItineraryResponse> {
    const { data } = await apiClient.post<ModifyItineraryResponse>(
      `/trips/${tripId}/activities/reorder`,
      payload
    );
    return data;
  },
};
