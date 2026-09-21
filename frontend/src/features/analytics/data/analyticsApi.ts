import { apiClient } from "@/core/api/apiClient";

export interface SCPMModelStatus {
  available: boolean;
  active?: boolean;
  status?: string;
  sample_count?: number;
  positive_count?: number;
  negative_count?: number;
  accuracy?: number | null;
  baseline_accuracy?: number | null;
  f1?: number | null;
  trained_at?: string | null;
  personalization_source?: string;
  error?: string;
}

export interface AnalyticsDashboardResult {
  user_id: string;
  travel_statistics: {
    total_trips_planned: number;
    total_destinations: number;
    total_days_planned: number;
    distance_and_carbon_tracking: string;
  };
  budget_analysis: {
    total_budget_allocated: number;
    total_estimated_cost: number;
    savings_rate_pct: number | null;
    note: string;
    category_split: string;
  };
  declared_interests: string[];
  memory_evolution: {
    active_inferred_preferences: number;
    behavioral_feature_weights: Record<string, number>;
  };
  personalization_model: SCPMModelStatus;
  recommendation_accuracy: null;
  recommendation_accuracy_note: string;
}

export interface TrainResponse {
  trained: boolean;
  status: string;
  sample_count: number;
  positive_count: number;
  negative_count: number;
  accuracy: number | null;
  baseline_accuracy: number | null;
  f1: number | null;
  message: string;
}

export interface ModelStatusResponse {
  active: boolean;
  status: string;
  model_version: string;
  sample_count: number;
  positive_count: number;
  negative_count: number;
  accuracy: number | null;
  baseline_accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  roc_auc: number | null;
  trained_at: string | null;
  last_updated: string;
  records_since_last_train: number;
  message: string;
}

export const analyticsApi = {
  async getDashboard(): Promise<AnalyticsDashboardResult> {
    const { data } = await apiClient.get<AnalyticsDashboardResult>("/analytics/dashboard");
    return data;
  },

  getExportCsvUrl(): string {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
    return `${baseUrl}/analytics/export-csv`;
  },
};

export const personalizationApi = {
  async trainModel(force = false): Promise<TrainResponse> {
    const { data } = await apiClient.post<TrainResponse>("/personalization/train", { force });
    return data;
  },

  async getModelStatus(): Promise<ModelStatusResponse> {
    const { data } = await apiClient.get<ModelStatusResponse>("/personalization/model-status");
    return data;
  },

  async getExplanation() {
    const { data } = await apiClient.get("/personalization/explanation");
    return data;
  },
};

