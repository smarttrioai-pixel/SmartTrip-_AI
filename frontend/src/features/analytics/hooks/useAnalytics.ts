import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/features/analytics/data/analyticsApi";

export function useAnalyticsDashboard() {
  return useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => analyticsApi.getDashboard(),
    staleTime: 1000 * 60 * 5,
  });
}
