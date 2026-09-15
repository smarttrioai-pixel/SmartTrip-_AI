"use client";

import { useCallback, useEffect, useState } from "react";

import type { LandmarkAnalysisResult } from "@/features/explore/data/exploreApi";
import type { Trip } from "@/features/itinerary/domain/types";
import {
  buildActivityNarration,
  buildDayOverview,
  buildLandmarkNarration,
  buildWelcomeMessage,
} from "@/features/tour-guide/lib/buildGuideScript";
import type { GuideMessage, GuidePhase } from "@/features/tour-guide/domain/types";
import { useSpeechGuide } from "@/features/tour-guide/hooks/useSpeechGuide";

function makeId() {
  return Math.random().toString(36).slice(2, 9);
}

function addMessage(messages: GuideMessage[], role: GuideMessage["role"], text: string): GuideMessage[] {
  return [...messages, { id: makeId(), role, text }];
}

export function useTourGuide(trip: Trip | undefined, userName: string) {
  const speech = useSpeechGuide();

  const [phase, setPhase] = useState<GuidePhase>("welcome");
  const [activityIndex, setActivityIndex] = useState(0);
  const [messages, setMessages] = useState<GuideMessage[]>([]);
  const [identifiedLandmark, setIdentifiedLandmark] = useState<LandmarkAnalysisResult | null>(null);
  const [showFullItinerary, setShowFullItinerary] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [hasGreeted, setHasGreeted] = useState(false);

  useEffect(() => {
    setPhase("welcome");
    setActivityIndex(0);
    setMessages([]);
    setIdentifiedLandmark(null);
    setShowFullItinerary(false);
    setCameraOpen(false);
    setHasGreeted(false);
    speech.stop();
  }, [trip?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const dayPlan = trip?.days[0];
  const activities = dayPlan?.activities ?? [];

  const greet = useCallback(() => {
    if (!trip || hasGreeted) return;
    const welcome = buildWelcomeMessage(userName, trip);
    setMessages((prev) => addMessage(prev, "guide", welcome));
    speech.speak(welcome);
    setHasGreeted(true);
  }, [trip, userName, hasGreeted, speech]);

  const startWalkthrough = useCallback(() => {
    if (!trip || !dayPlan) return;

    setPhase("walkthrough");
    setActivityIndex(0);
    setShowFullItinerary(false);

    const overview = buildDayOverview(trip, dayPlan.dayNumber);
    setMessages((prev) => addMessage(prev, "guide", overview));

    speech.speak(overview, () => {
      const first = activities[0];
      if (first) {
        const narration = buildActivityNarration(first, 0, activities.length);
        setMessages((prev) => addMessage(prev, "guide", narration));
        speech.speak(narration);
      }
    });
  }, [trip, dayPlan, activities, speech]);

  const narrateActivity = useCallback(
    (index: number) => {
      const activity = activities[index];
      if (!activity) return;

      setActivityIndex(index);
      const narration = buildActivityNarration(activity, index, activities.length);
      setMessages((prev) => addMessage(prev, "guide", narration));
      speech.speak(narration);
    },
    [activities, speech]
  );

  const nextActivity = useCallback(() => {
    const next = activityIndex + 1;
    if (next >= activities.length) {
      setPhase("finished");
      const done =
        "That's your full Day 1 plan! Tap 'Identify what I'm seeing' anytime to learn about landmarks around you, or ask me anything below.";
      setMessages((prev) => addMessage(prev, "guide", done));
      speech.speak(done);
      return;
    }
    narrateActivity(next);
  }, [activityIndex, activities.length, narrateActivity, speech]);

  const handleLandmarkIdentified = useCallback(
    (result: LandmarkAnalysisResult) => {
      setIdentifiedLandmark(result);
      const narration = buildLandmarkNarration(
        result.landmark_name,
        result.historical_background
      );
      setMessages((prev) => addMessage(prev, "guide", narration));
      speech.speak(narration);
      setCameraOpen(false);
    },
    [speech]
  );

  const askAboutCurrentContext = useCallback(
    async (question: string, answerHandler: (landmark: string, q: string) => Promise<string>) => {
      if (!question.trim()) return;

      setMessages((prev) => addMessage(prev, "user", question));

      const landmarkName =
        identifiedLandmark?.landmark_name ??
        activities[activityIndex]?.title ??
        trip?.destination ??
        "this destination";

      const answer = await answerHandler(landmarkName, question);
      setMessages((prev) => addMessage(prev, "guide", answer));
      speech.speak(answer);
    },
    [identifiedLandmark, activities, activityIndex, trip, speech]
  );

  const toggleFullItinerary = useCallback(() => {
    setShowFullItinerary((v) => !v);
  }, []);

  return {
    phase,
    activityIndex,
    messages,
    identifiedLandmark,
    showFullItinerary,
    cameraOpen,
    setCameraOpen,
    dayPlan,
    activities,
    speech,
    greet,
    startWalkthrough,
    narrateActivity,
    nextActivity,
    handleLandmarkIdentified,
    askAboutCurrentContext,
    toggleFullItinerary,
  };
}
