"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

// OpenFreeMap: free, no API key required, serves OpenStreetMap-derived
// vector tiles. Deliberately chosen over a key-gated provider (MapTiler,
// Stadia) after this session's OPENTRIPMAP_API_KEY lesson — a map that
// silently breaks because a key was never set is worse than one that
// just works.
const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";

export interface LatLon {
  lat: number;
  lon: number;
}

export interface MapViewProps {
  currentLocation?: LatLon | null;
  destination?: LatLon | null;
  /** GeoJSON LineString coordinates, [lon, lat] pairs — matches the shape the backend's /navigation/route already returns. */
  routeCoordinates?: [number, number][] | null;
  className?: string;
}

export function MapView({ currentLocation, destination, routeCoordinates, className }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  // Initialize the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    mapRef.current = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE_URL,
      center: [currentLocation?.lon ?? 0, currentLocation?.lat ?? 20],
      zoom: currentLocation ? 12 : 1.5,
    });
    mapRef.current.addControl(new maplibregl.NavigationControl(), "top-right");

    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update markers, route, and auto-fit bounds whenever the real data changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const applyUpdate = () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];

      const bounds = new maplibregl.LngLatBounds();
      let hasBounds = false;

      if (currentLocation) {
        const marker = new maplibregl.Marker({ color: "#12b76a" })
          .setLngLat([currentLocation.lon, currentLocation.lat])
          .setPopup(new maplibregl.Popup().setText("Your location"))
          .addTo(map);
        markersRef.current.push(marker);
        bounds.extend([currentLocation.lon, currentLocation.lat]);
        hasBounds = true;
      }

      if (destination) {
        const marker = new maplibregl.Marker({ color: "#ff7a3d" })
          .setLngLat([destination.lon, destination.lat])
          .setPopup(new maplibregl.Popup().setText("Destination"))
          .addTo(map);
        markersRef.current.push(marker);
        bounds.extend([destination.lon, destination.lat]);
        hasBounds = true;
      }

      // Route polyline as a GeoJSON source/layer — cleared and re-added on
      // every update since MapLibre doesn't let you mutate a source's data
      // shape (line vs none) in place cleanly for this use case.
      if (map.getLayer("route-line")) map.removeLayer("route-line");
      if (map.getSource("route")) map.removeSource("route");

      if (routeCoordinates && routeCoordinates.length > 1) {
        map.addSource("route", {
          type: "geojson",
          data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: routeCoordinates } },
        });
        map.addLayer({
          id: "route-line",
          type: "line",
          source: "route",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#12b76a", "line-width": 4, "line-opacity": 0.85 },
        });
        routeCoordinates.forEach((c) => bounds.extend(c as [number, number]));
        hasBounds = true;
      }

      if (hasBounds) {
        map.fitBounds(bounds, { padding: 60, maxZoom: 15, duration: 500 });
      }
    };

    if (map.isStyleLoaded()) {
      applyUpdate();
    } else {
      map.once("load", applyUpdate);
    }
  }, [currentLocation, destination, routeCoordinates]);

  return <div ref={containerRef} className={className ?? "h-full w-full"} />;
}
