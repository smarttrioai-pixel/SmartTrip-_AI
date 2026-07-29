"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Navigation, Navigation2, Volume2, Clock, AlertTriangle } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { useGeocode, useRoute, useNearbyPois } from "@/features/navigation/hooks/useNavigation";
import { useTrips } from "@/features/itinerary/hooks/useTrips";
import { MapView } from "@/shared/components/map/MapView";

export default function NavigationPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-ink-400">Loading navigation…</div>}>
      <NavigationPageContent />
    </Suspense>
  );
}

function NavigationPageContent() {
  const searchParams = useSearchParams();
  const destinationFromUrl = searchParams.get("destination");

  const { data: savedTrips } = useTrips(true);
  const activeTripDestination = savedTrips?.[0]?.destination ?? "";

  const [destination, setDestination] = useState(destinationFromUrl ?? activeTripDestination);
  const [travelMode, setTravelMode] = useState<"walking" | "driving" | "cycling">("driving");
  const [isNavigating, setIsNavigating] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);

  // If a PlaceCard's "Navigate" button linked here with a real destination,
  // prefer it over anything else once it's available.
  useEffect(() => {
    if (destinationFromUrl) setDestination(destinationFromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destinationFromUrl]);

  // Real current location via the browser's Geolocation API — the
  // previous version used hardcoded Paris coordinates (48.8566, 2.3522)
  // as "current location" for every user, everywhere.
  const [origin, setOrigin] = useState<{ lat: number; lon: number } | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("geolocation" in navigator)) {
      setGeoError("Geolocation is not supported by this browser.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setOrigin({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => setGeoError("Location access denied — enable it to get real routing from your position."),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  }, []);

  const { data: geocodeData, isLoading: isGeocoding, isError: isGeocodeError } = useGeocode(destination);

  // Only query a route once we have a REAL origin and a REAL geocoded
  // destination — not a Paris-area fallback shown regardless of input.
  const { data: routeData, isLoading: isRouting } = useRoute(
    origin?.lat ?? 0,
    origin?.lon ?? 0,
    geocodeData?.lat ?? 0,
    geocodeData?.lon ?? 0,
    travelMode
  );
  const hasRealRoute = Boolean(origin && geocodeData && routeData);

  const { data: poiData } = useNearbyPois(geocodeData?.lat ?? 0, geocodeData?.lon ?? 0);

  const handleVoiceNarration = () => {
    setIsVoiceActive(!isVoiceActive);
    if (!isVoiceActive && typeof window !== "undefined" && "speechSynthesis" in window && routeData) {
      const utterance = new SpeechSynthesisUtterance(
        `Starting turn by turn navigation toward ${destination}. Distance is ${routeData.distance_km} kilometers.`
      );
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto w-full">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <Navigation className="h-6 w-6 text-brand-600" /> MapLibre AI Navigation & Routing
          </h1>
          <p className="text-sm text-ink-500">Real-time route optimization, turn-by-turn ETA, and voice guidance</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={isVoiceActive ? "primary" : "outline"}
            onClick={handleVoiceNarration}
            disabled={!routeData}
            className="flex items-center gap-2"
          >
            <Volume2 className="h-4 w-4" /> {isVoiceActive ? "Voice Active" : "Voice Guidance"}
          </Button>
          <Button
            variant={isNavigating ? "outline" : "primary"}
            onClick={() => setIsNavigating(!isNavigating)}
            disabled={!hasRealRoute}
            className="flex items-center gap-2"
          >
            <Navigation2 className="h-4 w-4" /> {isNavigating ? "Stop Navigation" : "Take Me There"}
          </Button>
        </div>
      </div>

      {geoError && (
        <p className="flex items-center gap-2 text-sm text-sunset-600">
          <AlertTriangle className="h-4 w-4" /> {geoError}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls Sidebar */}
        <div className="flex flex-col gap-4 bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm">
          <div className="flex items-center gap-2">
            <Input
              label="Destination Search"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Search place or landmark..."
            />
          </div>
          {isGeocodeError && <p className="text-xs text-sunset-600">Could not find that place.</p>}

          <label className="text-xs font-semibold text-ink-500 uppercase tracking-wider mt-2">Travel Mode</label>
          <div className="grid grid-cols-3 gap-2">
            {(["walking", "cycling", "driving"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setTravelMode(mode)}
                className={`py-2 px-3 rounded-xl text-xs font-medium capitalize border transition-all ${
                  travelMode === mode
                    ? "bg-brand-50 border-brand-500 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                    : "border-ink-200 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-800"
                }`}
              >
                {mode}
              </button>
            ))}
          </div>

          <div className="mt-4 p-4 rounded-xl bg-ink-50 dark:bg-ink-800 flex items-center justify-between">
            <div>
              <p className="text-xs text-ink-500">Estimated Duration</p>
              <p className="text-lg font-bold text-ink-900 dark:text-white flex items-center gap-1">
                <Clock className="h-4 w-4 text-brand-600" />{" "}
                {isRouting || isGeocoding
                  ? "Calculating..."
                  : routeData
                    ? `${routeData.duration_minutes} mins (${routeData.distance_km} km)`
                    : "Enter a destination"}
              </p>
            </div>
          </div>

          <div className="mt-2">
            <h3 className="text-sm font-semibold text-ink-900 dark:text-white mb-3">Live Turn-by-Turn Guidance</h3>
            {!routeData ? (
              <p className="text-xs text-ink-400">Turn-by-turn steps will appear once a route is calculated.</p>
            ) : (
              <div className="flex flex-col gap-2 max-h-60 overflow-y-auto">
                {routeData.steps.map((step, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-2.5 rounded-lg border border-ink-100 dark:border-ink-800 text-xs">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 font-bold text-[10px]">
                      {idx + 1}
                    </span>
                    <div className="flex-1">
                      <p className="text-ink-800 dark:text-ink-200">{step.instruction}</p>
                      <p className="text-ink-400 font-medium">{step.distance_km} km</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {poiData && poiData.length > 0 && (
            <div className="mt-2 border-t border-ink-100 dark:border-ink-800 pt-3">
              <h3 className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">Nearby POIs</h3>
              <div className="flex flex-col gap-1.5">
                {poiData.slice(0, 3).map((poi) => (
                  <div key={poi.xid} className="flex items-center justify-between text-xs p-2 rounded-lg bg-ink-50 dark:bg-ink-800">
                    <span className="font-medium text-ink-800 dark:text-ink-200 truncate">{poi.name}</span>
                    <span className="text-[10px] text-brand-600 font-bold">★ {poi.rate}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Map Canvas */}
        <div className="lg:col-span-2 relative min-h-[500px] rounded-2xl overflow-hidden border border-ink-100 dark:border-ink-700 bg-ink-900 shadow-md">
          <MapView
            currentLocation={origin}
            destination={geocodeData ? { lat: geocodeData.lat, lon: geocodeData.lon } : null}
            routeCoordinates={routeData?.coordinates ?? null}
          />
          {!origin && !geocodeData && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-ink-900/70">
              <p className="text-xs text-ink-300 px-6 text-center">
                {geoError ? geoError : "Waiting for your location and a destination search…"}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
