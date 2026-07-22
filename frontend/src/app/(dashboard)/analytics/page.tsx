"use client";

import { useState } from "react";
import { BarChart3, Download, TrendingUp, Brain, PieChart, ShieldCheck, CheckCircle, Compass } from "lucide-react";
import { Button } from "@/shared/components/ui/button";

export default function AnalyticsPage() {
  const [isExporting, setIsExporting] = useState(false);

  const stats = {
    total_trips: 8,
    cities_visited: 12,
    total_km: 4250.0,
    days_traveled: 24,
    budget_allocated: 3200.0,
    actual_spent: 2980.0,
    recommendation_accuracy: 94.2,
    acceptance_rate: 88.0,
    memory_evolution_score: 88.0,
    categories: [
      { name: "Culture & Heritage", pct: 35, color: "bg-brand-500" },
      { name: "Gastronomy & Dining", pct: 28, color: "bg-indigo-500" },
      { name: "Architecture & Art", pct: 22, color: "bg-emerald-500" },
      { name: "Nature & Parks", pct: 15, color: "bg-amber-500" },
    ],
    preference_trends: [
      { feature: "Distance Tolerance", value: "+0.75 (Walk Friendly)" },
      { feature: "Budget Sensitivity", value: "-0.40 (Value Priority)" },
      { feature: "Crowd Aversion", value: "+0.60 (Prefers Quiet)" },
      { feature: "Pace Preference", value: "-0.20 (Relaxed Pace)" },
    ],
  };

  const handleExportCSV = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      window.open("http://localhost:8000/api/v1/analytics/export-csv", "_blank");
    }, 500);
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto w-full">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-ink-100 dark:border-ink-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-brand-600" /> Travel Analytics & Cognitive Intelligence
          </h1>
          <p className="text-sm text-ink-500">Track travel behavior, budget accuracy, memory evolution, and AI performance metrics</p>
        </div>
        <Button onClick={handleExportCSV} disabled={isExporting} className="flex items-center gap-2">
          <Download className="h-4 w-4" /> {isExporting ? "Exporting..." : "Export CSV Data"}
        </Button>
      </div>

      {/* Overview Stat Widgets */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Trips Planned</p>
          <p className="text-2xl font-bold text-ink-900 dark:text-white mt-1">{stats.total_trips}</p>
          <p className="text-xs text-brand-600 font-medium mt-1">{stats.cities_visited} Cities Visited</p>
        </div>

        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">AI Recommendation Accuracy</p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">{stats.recommendation_accuracy}%</p>
          <p className="text-xs text-ink-400 font-medium mt-1">{stats.acceptance_rate}% Acceptance Rate</p>
        </div>

        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Total Distance</p>
          <p className="text-2xl font-bold text-ink-900 dark:text-white mt-1">{stats.total_km} km</p>
          <p className="text-xs text-ink-400 font-medium mt-1">{stats.days_traveled} Total Days</p>
        </div>

        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Memory Evolution Score</p>
          <p className="text-2xl font-bold text-indigo-600 mt-1">{stats.memory_evolution_score}%</p>
          <p className="text-xs text-ink-400 font-medium mt-1">High Personalization</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Category Split Breakdown */}
        <div className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
          <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
            <PieChart className="h-5 w-5 text-brand-600" /> Visited Attraction Categories
          </h2>
          <div className="flex flex-col gap-3 mt-2">
            {stats.categories.map((cat, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                <div className="flex justify-between text-xs font-medium text-ink-800 dark:text-ink-200">
                  <span>{cat.name}</span>
                  <span>{cat.pct}%</span>
                </div>
                <div className="h-2 w-full bg-ink-100 dark:bg-ink-800 rounded-full overflow-hidden">
                  <div className={`h-full ${cat.color}`} style={{ width: `${cat.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Cognitive Preference Trends */}
        <div className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
          <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
            <Brain className="h-5 w-5 text-brand-600" /> Learned Behavioral Tendencies
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
            {stats.preference_trends.map((item, idx) => (
              <div key={idx} className="p-3.5 rounded-xl bg-ink-50 dark:bg-ink-800 border border-ink-100 dark:border-ink-700">
                <p className="text-xs text-ink-400 font-medium">{item.feature}</p>
                <p className="text-sm font-bold text-brand-700 dark:text-brand-300 mt-1">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
