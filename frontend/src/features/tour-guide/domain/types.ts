import type { Activity, Trip } from "@/features/itinerary/domain/types";
import type { LandmarkAnalysisResult } from "@/features/explore/data/exploreApi";

export type GuidePhase = "welcome" | "walkthrough" | "finished";

export interface GuideMessage {
  id: string;
  role: "guide" | "user";
  text: string;
}

export interface TourGuideState {
  phase: GuidePhase;
  activityIndex: number;
  messages: GuideMessage[];
  identifiedLandmark: LandmarkAnalysisResult | null;
  showFullItinerary: boolean;
  cameraOpen: boolean;
}

export interface DayTimelineProps {
  trip: Trip;
  dayNumber: number;
  activeActivityIndex: number | null;
  onSelectActivity: (index: number) => void;
}

export interface ActivityNarration {
  activity: Activity;
  index: number;
  total: number;
}
