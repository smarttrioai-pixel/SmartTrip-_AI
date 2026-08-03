import { apiClient } from "@/core/api/apiClient";
import type { EnrichPlaceInput, PlaceEnrichment } from "@/features/places/domain/types";

interface PlaceEnrichmentResultDto {
  found: boolean;
  matched_place_name: string | null;
  image_url: string | null;
  rating: number | null;
  rating_scale: string | null;
  reviews_count: number | null;
  reviews_count_note: string | null;
  category: string | null;
  address: string | null;
  opening_hours: string | null;
  opening_hours_note: string | null;
  estimated_ticket_price: number | null;
  estimated_ticket_price_note: string | null;
  lat: number | null;
  lon: number | null;
  wikipedia_summary: string | null;
}

function toEnrichment(dto: PlaceEnrichmentResultDto): PlaceEnrichment {
  return {
    found: dto.found,
    matchedPlaceName: dto.matched_place_name,
    imageUrl: dto.image_url,
    rating: dto.rating,
    ratingScale: dto.rating_scale,
    reviewsCount: dto.reviews_count,
    reviewsCountNote: dto.reviews_count_note,
    category: dto.category,
    address: dto.address,
    openingHours: dto.opening_hours,
    openingHoursNote: dto.opening_hours_note,
    estimatedTicketPrice: dto.estimated_ticket_price,
    estimatedTicketPriceNote: dto.estimated_ticket_price_note,
    lat: dto.lat,
    lon: dto.lon,
    wikipediaSummary: dto.wikipedia_summary,
  };
}

export const placesApi = {
  async enrichPlaces(destination: string, places: EnrichPlaceInput[]): Promise<PlaceEnrichment[]> {
    if (places.length === 0) return [];
    const { data } = await apiClient.post<{ results: PlaceEnrichmentResultDto[] }>("/places/enrich", {
      destination,
      places: places.map((p) => ({ title: p.title, location_hint: p.locationHint })),
    });
    return data.results.map(toEnrichment);
  },
};
