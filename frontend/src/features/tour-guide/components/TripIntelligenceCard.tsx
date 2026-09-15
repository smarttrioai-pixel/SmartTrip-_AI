"use client";

import { CloudSun, Wallet, MapPin, Cpu, ShieldCheck } from "lucide-react";

import type { Trip } from "@/features/itinerary/domain/types";

interface TripIntelligenceCardProps {
  trip: Trip;
}

export function TripIntelligenceCard({ trip }: TripIntelligenceCardProps) {
  const pipeline = trip.cognitiveTrace?.scif_pipeline;
  const budget = pipeline?.budget;
  const weather = pipeline?.weather;
  const memory = pipeline?.memory;
  const agents = pipeline?.agent_outputs ?? [];

  const day1Key = Object.keys(weather?.weather_days ?? {})[0];
  const day1Weather = day1Key ? weather?.weather_days[day1Key] : null;

  const verifiedCount = trip.days[0]?.activities.filter((a) => a.verified).length ?? 0;
  const totalActivities = trip.days[0]?.activities.length ?? 0;

  const items = [
    {
      icon: CloudSun,
      label: "Weather",
      value: day1Weather?.condition
        ? `${day1Weather.condition}${day1Weather.rain_probability != null && day1Weather.rain_probability > 40 ? " · rain likely" : ""}`
        : "Check forecast",
      color: "text-sky-600 dark:text-sky-400",
    },
    {
      icon: MapPin,
      label: "Places verified",
      value: totalActivities > 0 ? `${verifiedCount}/${totalActivities}` : "—",
      color: "text-emerald-600 dark:text-emerald-400",
    },
    {
      icon: Wallet,
      label: "Daily budget",
      value: budget?.daily_budget
        ? `${budget.currency ?? trip.currency} ${Math.round(budget.daily_budget).toLocaleString()}`
        : `${trip.currency} ${Math.round(trip.budget / Math.max(trip.days.length, 1)).toLocaleString()}`,
      color: "text-amber-600 dark:text-amber-400",
    },
    {
      icon: Cpu,
      label: "Agents active",
      value: agents.length > 0 ? String(agents.filter((a) => a.status === "ok").length) : "—",
      color: "text-purple-600 dark:text-purple-400",
    },
    {
      icon: ShieldCheck,
      label: "Trip confidence",
      value: pipeline ? "High" : "Standard",
      color: "text-brand-600 dark:text-brand-400",
    },
  ];

  if (memory?.items_retrieved) {
    items.push({
      icon: Cpu,
      label: "Memory used",
      value: `${memory.items_retrieved} preferences`,
      color: "text-ink-600 dark:text-ink-400",
    });
  }

  return (
    <div className="rounded-2xl border border-ink-100 bg-white p-4 dark:border-ink-700 dark:bg-ink-900">
      <h3 className="text-sm font-semibold text-ink-900 dark:text-white mb-3">Trip Intelligence</h3>
      <div className="grid grid-cols-2 gap-3">
        {items.slice(0, 6).map((item) => {
          const Icon = item.icon;
          return (
            <div
              key={item.label}
              className="rounded-xl border border-ink-100 bg-ink-50/50 p-3 dark:border-ink-800 dark:bg-ink-800/50"
            >
              <Icon className={`h-4 w-4 mb-1.5 ${item.color}`} aria-hidden="true" />
              <p className="text-[10px] font-medium uppercase tracking-wider text-ink-400">
                {item.label}
              </p>
              <p className="text-xs font-semibold text-ink-900 dark:text-white mt-0.5 truncate">
                {item.value}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
