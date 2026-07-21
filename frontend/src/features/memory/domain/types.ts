export interface PreferenceSummary {
  id: string;
  sourceText: string;
  sourceType: string;
  weight: number;
}

export interface InferredPreference {
  id: string;
  statement: string;
  confidence: number;
  supportingEventCount: number;
  status: string;
}

export interface MemoryInsights {
  preferences: PreferenceSummary[];
  inferredPreferences: InferredPreference[];
  featureWeights: Record<string, number>;
}

export const FEATURE_LABELS: Record<string, string> = {
  budget_sensitivity: "Budget sensitivity",
  crowd_aversion: "Crowd aversion",
  distance_tolerance: "Distance tolerance",
  novelty_seeking: "Novelty seeking",
  pace_preference: "Itinerary pace",
};
