import { apiClient } from "@/core/api/apiClient";

export interface GeocodeResult {
  lat: number;
  lon: number;
  display_name: string;
}

export interface RouteStep {
  instruction: string;
  distance_km: number;
}

export interface RouteResult {
  origin: { lat: number; lon: number };
  destination: { lat: number; lon: number };
  mode: string;
  distance_km: number;
  duration_minutes: number;
  eta_formatted: string;
  coordinates: [number, number][];
  steps: RouteStep[];
}

export interface PoiItem {
  xid: string;
  name: string;
  rate: number;
  kinds: string[];
  lat: number;
  lon: number;
  popularity_score: number;
}

export const navigationApi = {
  async geocode(query: string): Promise<GeocodeResult> {
    const { data } = await apiClient.get<GeocodeResult>("/navigation/geocode", {
      params: { q: query },
    });
    return data;
  },

  async calculateRoute(
    originLat: number,
    originLon: number,
    destLat: number,
    destLon: number,
    mode: string = "driving"
  ): Promise<RouteResult> {
    const { data } = await apiClient.get<RouteResult>("/navigation/route", {
      params: {
        origin_lat: originLat,
        origin_lon: originLon,
        dest_lat: destLat,
        dest_lon: destLon,
        mode,
      },
    });
    return data;
  },

  async getNearbyPois(lat: number, lon: number, radiusM: number = 5000): Promise<PoiItem[]> {
    const { data } = await apiClient.get<PoiItem[]>("/navigation/nearby", {
      params: { lat, lon, radius_m: radiusM },
    });
    return data;
  },
};
