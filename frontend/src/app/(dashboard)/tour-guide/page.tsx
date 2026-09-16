"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, AlertCircle, Compass } from "lucide-react";

import { useCurrentUser } from "@/features/authentication/hooks/useAuth";
import { exploreApi } from "@/features/explore/data/exploreApi";
import { useTrips } from "@/features/itinerary/hooks/useTrips";
import { CameraIdentifyPanel } from "@/features/tour-guide/components/CameraIdentifyPanel";
import { DayTimeline } from "@/features/tour-guide/components/DayTimeline";
import { GuideChatBubbles } from "@/features/tour-guide/components/GuideChatBubbles";
import { GuideInputBar } from "@/features/tour-guide/components/GuideInputBar";
import { TourGuideAvatar } from "@/features/tour-guide/components/TourGuideAvatar";
import { TripIntelligenceCard } from "@/features/tour-guide/components/TripIntelligenceCard";
import { useTourGuide } from "@/features/tour-guide/hooks/useTourGuide";
import { formatTripDuration } from "@/features/tour-guide/lib/buildGuideScript";

export default function TourGuidePage() {
  const { data: user } = useCurrentUser();
  const { data: savedTrips, isLoading: tripsLoading } = useTrips(true);
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);

  useEffect(() => {
    const firstTrip = savedTrips?.[0];
    if (firstTrip && !selectedTripId) {
      setSelectedTripId(firstTrip.id);
    }
  }, [savedTrips, selectedTripId]);

  const activeTrip = savedTrips?.find((t) => t.id === selectedTripId);
  const firstName = user?.fullName?.split(" ")[0] ?? "Explorer";

  const guide = useTourGuide(activeTrip, firstName);

  useEffect(() => {
    if (activeTrip) {
      guide.greet();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTrip?.id]);

  const handleAsk = async (question: string) => {
    setIsAsking(true);
    try {
      await guide.askAboutCurrentContext(question, async (landmark, q) => {
        const { answer } = await exploreApi.askQuestion(landmark, q);
        return answer;
      });
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6 max-w-[1400px] mx-auto w-full min-h-screen">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-ink-100 dark:border-ink-800 pb-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <Bot className="h-6 w-6 text-brand-600" />
            AI Tour Guide
          </h1>
          {activeTrip ? (
            <p className="text-sm text-ink-500 mt-0.5">
              {activeTrip.destination} · {formatTripDuration(activeTrip)} · {activeTrip.startDate}
            </p>
          ) : (
            <p className="text-sm text-ink-500">Select a saved trip to start your guided tour</p>
          )}
        </div>

        {savedTrips && savedTrips.length > 1 && (
          <div className="flex flex-wrap gap-2">
            {savedTrips.map((trip) => (
              <button
                key={trip.id}
                type="button"
                onClick={() => setSelectedTripId(trip.id)}
                className={`px-3 py-1.5 rounded-xl text-sm font-medium border transition-colors ${
                  selectedTripId === trip.id
                    ? "bg-brand-50 border-brand-500 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                    : "bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-700 text-ink-600 hover:bg-ink-50"
                }`}
              >
                {trip.destination}
              </button>
            ))}
          </div>
        )}
      </div>

      {tripsLoading && (
        <p className="text-sm text-ink-400">Loading your trips…</p>
      )}

      {!tripsLoading && savedTrips?.length === 0 && (
        <div className="rounded-2xl border border-dashed border-ink-200 p-10 text-center dark:border-ink-700">
          <AlertCircle className="h-10 w-10 text-ink-300 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-ink-900 dark:text-white">No saved trips yet</h2>
          <p className="text-sm text-ink-500 mt-1 max-w-md mx-auto">
            Save a trip from the Trip Planner first, then your AI guide can walk you through Day 1.
          </p>
          <Link
            href="/trip-planner"
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            <Compass className="h-4 w-4" />
            Plan a trip
          </Link>
        </div>
      )}

      {activeTrip && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-5">
          {/* Left: chat bubbles */}
          <div className="lg:col-span-3 order-2 lg:order-1">
            <GuideChatBubbles
              messages={guide.messages}
              phase={guide.phase}
              onStartWalkthrough={guide.startWalkthrough}
              onShowItinerary={guide.toggleFullItinerary}
              onNextActivity={guide.nextActivity}
              showFullItinerary={guide.showFullItinerary}
              hasActivities={guide.activities.length > 0}
            />
          </div>

          {/* Center: avatar + input */}
          <div className="lg:col-span-5 flex flex-col gap-4 order-1 lg:order-2">
            <TourGuideAvatar
              destination={activeTrip.destination}
              subtitle={guide.speech.subtitle}
              isSpeaking={guide.speech.isSpeaking}
              isPaused={guide.speech.isPaused}
              onTogglePause={guide.speech.togglePause}
              onStopSpeech={guide.speech.stop}
              onOpenCamera={() => guide.setCameraOpen(true)}
            />
            <GuideInputBar
              onAsk={handleAsk}
              isLoading={isAsking}
              disabled={!activeTrip}
            />
          </div>

          {/* Right: timeline + intelligence */}
          <div className="lg:col-span-4 flex flex-col gap-4 order-3">
            <DayTimeline
              trip={activeTrip}
              dayNumber={1}
              activeActivityIndex={guide.phase === "walkthrough" ? guide.activityIndex : null}
              onSelectActivity={guide.narrateActivity}
              expanded={guide.showFullItinerary}
            />
            <TripIntelligenceCard trip={activeTrip} />
          </div>
        </div>
      )}

      <CameraIdentifyPanel
        open={guide.cameraOpen}
        onClose={() => guide.setCameraOpen(false)}
        onIdentified={guide.handleLandmarkIdentified}
        promptHint={activeTrip?.destination ?? ""}
      />
    </div>
  );
}
