"use client";

import { BarChart3, Download, Brain, PieChart } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { useAnalyticsDashboard } from "@/features/analytics/hooks/useAnalytics";
import { analyticsApi } from "@/features/analytics/data/analyticsApi";

export default function AnalyticsPage() {
  const { data: analytics, isLoading } = useAnalyticsDashboard();

  const handleExportCSV = () => {
    window.open(analyticsApi.getExportCsvUrl(), "_blank");
  };

  const travelStats = analytics?.travel_statistics;
  const memoryEvolution = analytics?.memory_evolution;
  // behavioral_feature_weights are real values in the -1..1 range (from
  // Memory Engine's accept/reject learning) — displayed as a 0-100%
  // magnitude so the existing "X% Confidence" card format still applies.
  const behavioralTendencies = Object.entries(memoryEvolution?.behavioral_feature_weights ?? {}).map(
    ([feature, weight]) => ({
      category: feature.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      pct: Math.round(Math.abs(weight) * 100),
    })
  );

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto w-full">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-ink-100 dark:border-ink-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-brand-600" /> Travel Analytics & Cognitive Intelligence
          </h1>
          <p className="text-sm text-ink-500">Track travel behavior, budget accuracy, memory evolution, and AI performance metrics</p>
        </div>
        <Button onClick={handleExportCSV} className="flex items-center gap-2">
          <Download className="h-4 w-4" /> Export CSV Data
        </Button>
      </div>

      {isLoading && <p className="text-sm text-ink-400">Loading travel analytics...</p>}

      {/* Overview Stat Widgets */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Trips Planned</p>
          <p className="text-2xl font-bold text-ink-900 dark:text-white mt-1">{travelStats?.total_trips_planned ?? "—"}</p>
          <p className="text-xs text-brand-600 font-medium mt-1">{travelStats?.total_destinations ?? 0} Destinations Visited</p>
        </div>

        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">AI Recommendation Accuracy</p>
          <p className="text-2xl font-bold text-ink-400 mt-1">Not yet measurable</p>
          <p className="text-xs text-ink-400 font-medium mt-1">Requires an evaluation harness with user feedback (planned)</p>
        </div>

        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Distance Traveled</p>
          <p className="text-2xl font-bold text-ink-400 mt-1">Not yet tracked</p>
          <p className="text-xs text-ink-400 font-medium mt-1">{travelStats?.total_days_planned ?? 0} Total Days Planned</p>
        </div>

        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Preferences Learned</p>
          <p className="text-2xl font-bold text-indigo-600 mt-1">{memoryEvolution?.active_inferred_preferences ?? 0}</p>
          <p className="text-xs text-ink-400 font-medium mt-1">From your travel behavior over time</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category Split Breakdown */}
        <div className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
          <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
            <PieChart className="h-5 w-5 text-brand-600" /> Visited Attraction Categories
          </h2>
          <p className="text-sm text-ink-400">
            Not yet available — activities aren't currently categorized by type. This will populate
            once itinerary generation tags each activity's category.
          </p>
        </div>

        {/* Cognitive Preference Trends */}
        <div className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
          <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
            <Brain className="h-5 w-5 text-brand-600" /> Learned Behavioral Tendencies
          </h2>
          {behavioralTendencies.length === 0 ? (
            <p className="text-sm text-ink-400">
              Not enough trip activity yet — this fills in as you accept, reject, or save trips.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
              {behavioralTendencies.map((item, idx) => (
                <div key={idx} className="p-3.5 rounded-xl bg-ink-50 dark:bg-ink-800 border border-ink-100 dark:border-ink-700">
                  <p className="text-xs text-ink-400 font-medium">{item.category}</p>
                  <p className="text-sm font-bold text-brand-700 dark:text-brand-300 mt-1">{item.pct}% Strength</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
