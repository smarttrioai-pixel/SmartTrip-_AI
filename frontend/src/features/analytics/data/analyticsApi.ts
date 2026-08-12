import { apiClient } from "@/core/api/apiClient";

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
  recommendation_accuracy: null;
  recommendation_accuracy_note: string;
}

export const analyticsApi = {
  async getDashboard(): Promise<AnalyticsDashboardResult> {
    // Backend now identifies the user via the Firebase auth token
    // (CurrentUser), not a client-supplied user_id — the previous
    // `?user_id=` query param was removed since it let any caller request
    // any user's analytics.
    const { data } = await apiClient.get<AnalyticsDashboardResult>("/analytics/dashboard");
    return data;
  },

  getExportCsvUrl(): string {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
    return `${baseUrl}/analytics/export-csv`;
  },
};
