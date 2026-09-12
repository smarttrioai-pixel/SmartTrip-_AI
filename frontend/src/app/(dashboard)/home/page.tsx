"use client";

import {
  Compass,
  MapPinned,
  MessageCircle,
  Brain,
  TrendingUp,
  Calendar,
  BarChart3,
} from "lucide-react";
import Link from "next/link";

import { useCurrentUser } from "@/features/authentication/hooks/useAuth";
import { useTrips } from "@/features/itinerary/hooks/useTrips";
import { useMemoryInsights } from "@/features/memory/hooks/useMemory";
import { useAnalyticsDashboard } from "@/features/analytics/hooks/useAnalytics";
import { TripCard } from "@/features/itinerary/components/TripCard";

const QUICK_ACTIONS = [
  {
    href: "/trip-planner",
    label: "Plan a new trip",
    description: "AI itinerary with SCIF intelligence",
    icon: Compass,
    color: "brand",
  },
  {
    href: "/chat",
    label: "Ask the AI guide",
    description: "Travel questions & recommendations",
    icon: MessageCircle,
    color: "purple",
  },
  {
    href: "/saved-trips",
    label: "Saved trips",
    description: "View and manage your itineraries",
    icon: MapPinned,
    color: "sky",
  },
  {
    href: "/memory",
    label: "Cognitive Memory",
    description: "What SmartTrip has learned about you",
    icon: Brain,
    color: "amber",
  },
];

const COLOR_MAP: Record<string, string> = {
  brand: "bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400",
  purple: "bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400",
  sky: "bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-400",
  amber: "bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400",
};

export default function DashboardHomePage() {
  const { data: user } = useCurrentUser();
  const { data: trips, isLoading: tripsLoading } = useTrips();
  const { data: memory } = useMemoryInsights();
  const { data: analytics } = useAnalyticsDashboard();

  const recentTrips = trips?.slice(0, 3) ?? [];

  // Active inferred preferences count from memory
  const inferredCount =
    memory?.inferredPreferences?.filter((p) => p.status === "active").length ?? 0;

  // Analytics stats (from real backend data)
  const totalTrips = analytics?.travel_statistics?.total_trips_planned ?? recentTrips.length;
  const totalDays = analytics?.travel_statistics?.total_days_planned ?? 0;
  const totalDestinations = analytics?.travel_statistics?.total_destinations ?? 0;

  const firstName = user?.fullName?.split(" ")[0] ?? "Explorer";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Welcome */}
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">
          Welcome back, {firstName}
        </h1>
        <p className="mt-1 text-sm text-ink-400 dark:text-ink-500">
          Your SCIF-powered travel intelligence platform
        </p>
      </div>

      {/* Stats row — from real analytics data */}
      {analytics && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            icon={Compass}
            label="Trips planned"
            value={totalTrips}
            color="brand"
          />
          <StatCard
            icon={MapPinned}
            label="Destinations"
            value={totalDestinations}
            color="sky"
          />
          <StatCard
            icon={Calendar}
            label="Days planned"
            value={totalDays}
            color="purple"
          />
          <StatCard
            icon={Brain}
            label="Learned preferences"
            value={inferredCount}
            color="amber"
          />
        </div>
      )}

      {/* Quick actions */}
      <div className="mt-8">
        <h2 className="mb-3 font-display text-base font-semibold text-ink-900 dark:text-white">
          Quick actions
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <Link
                key={action.href}
                href={action.href}
                className="flex flex-col gap-3 rounded-2xl border border-ink-100 bg-white p-4 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-md dark:border-ink-700 dark:bg-ink-800"
              >
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-xl ${COLOR_MAP[action.color]}`}
                >
                  <Icon className="h-4.5 w-4.5" aria-hidden="true" />
                </div>
                <div>
                  <p className="font-medium text-ink-900 dark:text-white text-sm">
                    {action.label}
                  </p>
                  <p className="text-xs text-ink-400 dark:text-ink-500 mt-0.5">
                    {action.description}
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Memory intelligence snapshot */}
      {memory && inferredCount > 0 && (
        <div className="mt-8 rounded-2xl border border-amber-100 bg-amber-50/50 p-5 dark:border-amber-900/30 dark:bg-amber-950/20">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-100 dark:bg-amber-900/40">
              <Brain className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-semibold text-ink-900 dark:text-white">
                Memory Intelligence Active
              </p>
              <p className="text-xs text-ink-500 dark:text-ink-400">
                {inferredCount} learned preference{inferredCount !== 1 ? "s" : ""} shape your itineraries
              </p>
            </div>
            <Link
              href="/memory"
              className="ml-auto text-xs font-medium text-amber-600 hover:underline dark:text-amber-400"
            >
              View all →
            </Link>
          </div>
          <div className="flex flex-wrap gap-2">
            {memory.inferredPreferences
              .filter((p) => p.status === "active")
              .slice(0, 4)
              .map((p) => (
                <span
                  key={p.id}
                  className="rounded-lg bg-white px-2.5 py-1 text-xs text-ink-700 shadow-sm border border-amber-100 dark:border-amber-900/30 dark:bg-ink-800 dark:text-ink-300"
                >
                  {p.statement}
                </span>
              ))}
          </div>
        </div>
      )}

      {/* Analytics highlight */}
      {analytics?.budget_analysis && (
        <div className="mt-5 rounded-2xl border border-brand-100 bg-brand-50/30 p-5 dark:border-brand-900/30 dark:bg-brand-950/10">
          <div className="flex items-center gap-3 mb-2">
            <BarChart3 className="h-4 w-4 text-brand-500" />
            <p className="text-sm font-semibold text-ink-900 dark:text-white">Budget Overview</p>
            <Link href="/analytics" className="ml-auto text-xs font-medium text-brand-600 hover:underline dark:text-brand-400">
              Full analytics →
            </Link>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 text-sm">
            <div>
              <p className="text-xs text-ink-400">Total allocated</p>
              <p className="font-semibold text-ink-900 dark:text-white">
                {analytics.budget_analysis.total_budget_allocated.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-400">Total estimated cost</p>
              <p className="font-semibold text-ink-900 dark:text-white">
                {analytics.budget_analysis.total_estimated_cost.toLocaleString()}
              </p>
            </div>
            {analytics.budget_analysis.savings_rate_pct != null && (
              <div>
                <p className="text-xs text-ink-400">Savings rate</p>
                <p className="font-semibold text-green-600 dark:text-green-400">
                  {analytics.budget_analysis.savings_rate_pct.toFixed(1)}%
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Recent trips */}
      <div className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-base font-semibold text-ink-900 dark:text-white">
            Recent trips
          </h2>
          <Link
            href="/saved-trips"
            className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
          >
            View all
          </Link>
        </div>

        {tripsLoading && (
          <div className="grid gap-3 sm:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-36 rounded-2xl border border-ink-100 bg-white animate-pulse dark:border-ink-700 dark:bg-ink-800"
              />
            ))}
          </div>
        )}

        {!tripsLoading && recentTrips.length === 0 && (
          <div className="rounded-2xl border border-dashed border-ink-100 p-8 text-center dark:border-ink-700">
            <TrendingUp className="mx-auto h-8 w-8 text-ink-200 dark:text-ink-700 mb-3" />
            <p className="text-sm font-medium text-ink-600 dark:text-ink-400">No trips yet</p>
            <p className="mt-1 text-xs text-ink-400 dark:text-ink-500">
              Start with the AI Trip Planner to generate your first itinerary.
            </p>
            <Link
              href="/trip-planner"
              className="mt-3 inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              <Compass className="h-4 w-4" />
              Plan a trip
            </Link>
          </div>
        )}

        {!tripsLoading && recentTrips.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-3">
            {recentTrips.map((trip) => (
              <Link key={trip.id} href="/saved-trips">
                <TripCard trip={trip} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Stat card ─────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="rounded-2xl border border-ink-100 bg-white p-4 dark:border-ink-700 dark:bg-ink-800">
      <div className={`mb-2 flex h-8 w-8 items-center justify-center rounded-xl ${COLOR_MAP[color]}`}>
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <p className="text-xl font-bold text-ink-900 dark:text-white">{value}</p>
      <p className="text-xs text-ink-400 dark:text-ink-500 mt-0.5">{label}</p>
    </div>
  );
}
