import { apiClient } from "@/core/api/apiClient";
import type { InferredPreference, MemoryInsights, PreferenceSummary } from "@/features/memory/domain/types";

interface PreferenceSummaryDto {
  id: string;
  source_text: string;
  source_type: string;
  weight: number;
}

interface InferredPreferenceDto {
  id: string;
  statement: string;
  confidence: number;
  supporting_event_count: number;
  status: string;
}

interface MemoryInsightsDto {
  preferences: PreferenceSummaryDto[];
  inferred_preferences: InferredPreferenceDto[];
  feature_weights: Record<string, number>;
}

function toPreference(dto: PreferenceSummaryDto): PreferenceSummary {
  return { id: dto.id, sourceText: dto.source_text, sourceType: dto.source_type, weight: dto.weight };
}

function toInferred(dto: InferredPreferenceDto): InferredPreference {
  return {
    id: dto.id,
    statement: dto.statement,
    confidence: dto.confidence,
    supportingEventCount: dto.supporting_event_count,
    status: dto.status,
  };
}

export const memoryApi = {
  async getInsights(): Promise<MemoryInsights> {
    const { data } = await apiClient.get<MemoryInsightsDto>("/memory/insights");
    return {
      preferences: data.preferences.map(toPreference),
      inferredPreferences: data.inferred_preferences.map(toInferred),
      featureWeights: data.feature_weights,
    };
  },

  async savePreference(sourceText: string): Promise<void> {
    await apiClient.post("/memory/preferences", { source_text: sourceText, source_type: "explicit_interest" });
  },

  async rejectInference(inferenceId: string): Promise<void> {
    await apiClient.post(`/memory/inferences/${inferenceId}/reject`);
  },
};
