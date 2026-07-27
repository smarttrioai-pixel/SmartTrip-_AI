import { useQuery } from "@tanstack/react-query";
import { navigationApi } from "@/features/navigation/data/navigationApi";

export function useGeocode(query: string) {
  return useQuery({
    queryKey: ["navigation", "geocode", query],
    queryFn: () => navigationApi.geocode(query),
    enabled: Boolean(query && query.trim().length > 2),
    staleTime: 1000 * 60 * 30, // Cache for 30 minutes
  });
}

export function useRoute(
  originLat: number,
  originLon: number,
  destLat: number,
  destLon: number,
  mode: string = "driving"
) {
  return useQuery({
    queryKey: ["navigation", "route", originLat, originLon, destLat, destLon, mode],
    queryFn: () => navigationApi.calculateRoute(originLat, originLon, destLat, destLon, mode),
    enabled: Boolean(originLat && destLat),
    staleTime: 1000 * 60 * 5,
  });
}

export function useNearbyPois(lat: number, lon: number, radiusM: number = 5000) {
  return useQuery({
    queryKey: ["navigation", "nearby", lat, lon, radiusM],
    queryFn: () => navigationApi.getNearbyPois(lat, lon, radiusM),
    enabled: Boolean(lat && lon),
    staleTime: 1000 * 60 * 15,
  });
}
