export interface PlaceEnrichment {
  found: boolean;
  matchedPlaceName: string | null;
  imageUrl: string | null;
  rating: number | null;
  ratingScale: string | null;
  reviewsCount: number | null;
  reviewsCountNote: string | null;
  category: string | null;
  address: string | null;
  openingHours: string | null;
  openingHoursNote: string | null;
  estimatedTicketPrice: number | null;
  estimatedTicketPriceNote: string | null;
  lat: number | null;
  lon: number | null;
  wikipediaSummary: string | null;
  /** Geoapify is the primary provider. Value: "geoapify" */
  source: string | null;
  /** Geoapify place_id for deduplication and debugging */
  sourceId: string | null;
}

export interface EnrichPlaceInput {
  title: string;
  locationHint: string;
  category?: string;
  mealType?: string;
  foodQuery?: string;
}
