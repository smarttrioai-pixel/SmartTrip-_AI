import type { CognitiveTrace } from "@/features/itinerary/domain/scif-types";

export type { CognitiveTrace };

export interface Explanation {
  reasonText: string;
  budgetMatch: number;
  interestMatch: number;
  weatherMatch: number;      // mapped from weather_match
  contextScore: number;
  confidence: number;
  /** Personalization score from behavioral memory. Null on old trips. */
  personalizationScore?: number | null;
  unavailableFactors: string[]; // mapped from unavailable_factors
}


export interface PlaceEnrichmentInline {
  found: boolean;
  matchedPlaceName?: string | null;
  imageUrl?: string | null;
  rating?: number | null;
  ratingScale?: string | null;
  reviewsCount?: number | null;
  address?: string | null;
  openingHours?: string | null;
  lat?: number | null;
  lon?: number | null;
  category?: string | null;
  source?: string | null;
  sourceId?: string | null;
}

export interface Activity {
  time: string;
  title: string;
  description: string;
  location: string;
  estimatedCost: number;
  category?: string | null;
  reason?: string | null;
  mealType?: string | null;
  foodQuery?: string | null;
  explanation: Explanation | null;
  // Inline place data returned directly from trip generate endpoint
  placeEnrichment?: PlaceEnrichmentInline | null;
  // SCIF Pass 2 rejection (from backend)
  scifRejected?: boolean | null;
  scifRejectionReason?: string | null;
  // Google/Geoapify verification data (from backend Activity schema)
  verified?: boolean | null;
  placeProvider?: string | null;    // "google" | "geoapify"
  placeId?: string | null;          // Google place_id
  rating?: number | null;           // 0-5 Google rating
  userRatingsTotal?: number | null; // Google review count
  slotIntent?: string | null;       // Qwen-generated intent before enrichment
}

export interface DayPlan {
  dayNumber: number;
  title: string;
  activities: Activity[];
}

export interface Trip {
  id: string;
  destination: string;
  startDate: string;
  endDate: string;
  budget: number;
  currency: string;
  travelStyle: string;
  days: DayPlan[];
  estimatedTotalCost: number;
  isSaved: boolean;
  // SCIF cognitive trace — present on newly generated trips, null on old ones
  cognitiveTrace: CognitiveTrace | null;
}

export interface GenerateItineraryPayload {
  destination: string;
  startDate: string;
  endDate: string;
  budget: number;
  currency: string;
  travelStyle: string;
  interests: string[];
  transport: string;
}
