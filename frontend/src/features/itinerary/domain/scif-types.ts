// ────────────────────────────────────────────────────────────────────────────
// SCIF-specific types for cognitive_trace returned by the backend
// These mirror the CognitivePlanningContext.to_trace_dict() output exactly.
// ────────────────────────────────────────────────────────────────────────────

export interface AgentOutput {
  agent: string;
  status: "ok" | "unavailable" | "error";
  data_source: string;
  contribution: string;
  items_returned: number;
  latency_ms: number;
  details: Record<string, unknown>;
}

export interface PipelineStage {
  stage: string;
  component: string;
  status: "ok" | "skipped" | "error";
  summary: string;
  latency_ms: number;
  items: number;
  data_source: string;
}

export interface BudgetSummary {
  total_budget: number;
  currency: string;
  num_days: number;
  daily_budget: number;
  meal_budget_per_day: number;
  activity_budget_per_day: number;
  transport_budget_per_day: number;
  accommodation_budget_per_day: number;
  tier: "budget" | "mid_range" | "luxury";
  constraints: string[];
  source: string;
}

export interface WeatherDay {
  date: string;
  status: "available" | "unavailable";
  condition: string | null;
  temperature_max: number | null;
  temperature_min: number | null;
  rain_probability: number | null;
  precipitation_mm: number | null;
  wind_speed: number | null;
  is_suitable_outdoor: boolean;
  suitability_score: number;
  source: string;
}

export interface ScifWeatherSummary {
  available_sources: string[];
  unavailable_sources: string[];
  weather_days: Record<string, WeatherDay>;
  opening_hours_places: number;
  current_datetime: string | null;
}

export interface ScifPipeline {
  destination: string;
  dates: string;
  num_days: number;
  coordinates: {
    lat: number | null;
    lon: number | null;
    source: string;
  };
  memory: {
    items_retrieved: number;
    source: string;
    summary: string;
  };
  profile: {
    food_preference: string;
    travel_style: string;
    interests: string[];
  };
  budget: Partial<BudgetSummary>;
  weather: ScifWeatherSummary;
  weather_constraints: string[];
  scif_constraints: string[];
  agent_outputs: AgentOutput[];
  pipeline_stages: PipelineStage[];
}

/**
 * The full cognitive_trace object returned by the backend on every
 * POST /trips/generate response. Some fields may be missing for older
 * trips (nullable for backward-compatibility).
 */
export interface CognitiveTrace {
  // Old-format fields (pre-SCIFOrchestrator, may still be present)
  current_request?: Record<string, unknown>;
  memory_used?: boolean;
  memory_items?: number;
  live_context?: Record<string, unknown>;
  constraints_count?: number;
  scif_decisions?: Array<{
    place: string;
    decision: string;
    reason: string;
    evidence: Record<string, unknown>;
    confidence: number;
    suggested_time?: string;
  }>;
  place_provider?: string;
  candidate_stats?: Record<string, number>;
  rejected_slots?: Array<Record<string, unknown>>;

  // New-format: full SCIF pipeline trace (post-SCIFOrchestrator)
  scif_pipeline?: ScifPipeline;
}
