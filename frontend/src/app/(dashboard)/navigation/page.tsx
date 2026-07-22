"use client";

import { useState } from "react";
import { Navigation, MapPin, Navigation2, Volume2, ShieldCheck, Clock, Compass } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

export default function NavigationPage() {
  const [destination, setDestination] = useState("Eiffel Tower, Paris");
  const [travelMode, setTravelMode] = useState<"walking" | "driving" | "cycling">("walking");
  const [isNavigating, setIsNavigating] = useState(false);
  const [isVoiceActive, setIsVoiceActive] = useState(false);

  const steps = [
    { instruction: "Head east on Rue de Rivoli toward Place de la Concorde", distance: "350 m" },
    { instruction: "Turn right onto Pont de la Concorde", distance: "450 m" },
    { instruction: "Continue onto Boulevard Saint-Germain", distance: "800 m" },
    { instruction: "Arrive at destination point on right", distance: "50 m" },
  ];

  const handleVoiceNarration = () => {
    setIsVoiceActive(!isVoiceActive);
    if (!isVoiceActive && typeof window !== "undefined" && "speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance("Starting turn by turn navigation toward " + destination);
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
            variant={isVoiceActive ? "primary" : "secondary"}
            onClick={handleVoiceNarration}
            className="flex items-center gap-2"
          >
            <Volume2 className="h-4 w-4" /> {isVoiceActive ? "Voice On" : "Voice Guidance"}
          </Button>
          <Button
            variant={isNavigating ? "secondary" : "primary"}
            onClick={() => setIsNavigating(!isNavigating)}
            className="flex items-center gap-2"
          >
            <Navigation2 className="h-4 w-4" /> {isNavigating ? "Stop Navigation" : "Take Me There"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Navigation Sidebar & Controls */}
        <div className="flex flex-col gap-4 bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm">
          <label className="text-xs font-semibold text-ink-500 uppercase tracking-wider">Destination Search</label>
          <div className="flex items-center gap-2">
            <Input
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Search place or landmark..."
            />
          </div>

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
                <Clock className="h-4 w-4 text-brand-600" /> 18 mins (1.6 km)
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-ink-500">Safety Status</p>
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded-md">
                <ShieldCheck className="h-3.5 w-3.5" /> High Safety
              </span>
            </div>
          </div>

          <div className="mt-2">
            <h3 className="text-sm font-semibold text-ink-900 dark:text-white mb-3">Turn-by-Turn Guidance</h3>
            <div className="flex flex-col gap-2">
              {steps.map((step, idx) => (
                <div key={idx} className="flex items-start gap-3 p-2.5 rounded-lg border border-ink-100 dark:border-ink-800 text-xs">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 font-bold text-[10px]">
                    {idx + 1}
                  </span>
                  <div className="flex-1">
                    <p className="text-ink-800 dark:text-ink-200">{step.instruction}</p>
                    <p className="text-ink-400 font-medium">{step.distance}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Map Display Simulation Canvas */}
        <div className="lg:col-span-2 relative min-h-[500px] rounded-2xl overflow-hidden border border-ink-100 dark:border-ink-700 bg-ink-900 shadow-md flex items-center justify-center text-white">
          <div className="absolute inset-0 bg-[radial-gradient(#3b82f6_1px,transparent_1px)] [background-size:16px_16px] opacity-20" />
          <div className="relative z-10 flex flex-col items-center gap-4 text-center p-6 bg-ink-950/80 backdrop-blur-md rounded-2xl border border-ink-700 max-w-md">
            <div className="h-16 w-16 rounded-full bg-brand-600/20 flex items-center justify-center text-brand-400 animate-pulse">
              <Compass className="h-8 w-8" />
            </div>
            <h2 className="text-lg font-bold">Interactive MapLibre Canvas Ready</h2>
            <p className="text-xs text-ink-300">
              OpenStreetMap vector tiles loaded. Active route generated for <span className="text-brand-400 font-semibold">{destination}</span> via {travelMode}.
            </p>
            <div className="flex items-center gap-2 text-xs text-emerald-400 font-mono">
              <MapPin className="h-4 w-4" /> Coordinates: [48.8566, 2.3522] → [48.8606, 2.3376]
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
