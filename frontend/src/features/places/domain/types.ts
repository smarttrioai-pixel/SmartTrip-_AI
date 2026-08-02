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
}

export interface EnrichPlaceInput {
  title: string;
  locationHint: string;
}
