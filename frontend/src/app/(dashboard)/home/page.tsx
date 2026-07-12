"use client";

import { Compass, MapPinned, MessageCircle } from "lucide-react";
import Link from "next/link";

import { useCurrentUser } from "@/features/authentication/hooks/useAuth";

const QUICK_ACTIONS = [
  { href: "/trip-planner", label: "Plan a new trip", description: "Generate an AI itinerary", icon: Compass },
  { href: "/chat", label: "Ask the AI guide", description: "Get travel questions answered", icon: MessageCircle },
  { href: "/saved-trips", label: "View saved trips", description: "See your trips on a map", icon: MapPinned },
];

export default function DashboardHomePage() {
  const { data: user } = useCurrentUser();

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">
        {user ? `Welcome back, ${user.fullName.split(" ")[0]}` : "Welcome back"}
      </h1>
      <p className="mt-1 text-sm text-ink-400">Where to next?</p>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <Link
              key={action.href}
              href={action.href}
              className="flex flex-col gap-3 rounded-2xl border border-ink-100 bg-white p-5 shadow-card transition-transform hover:-translate-y-0.5 dark:border-ink-700 dark:bg-ink-800"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-300">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
              <div>
                <p className="font-medium text-ink-900 dark:text-white">{action.label}</p>
                <p className="text-sm text-ink-400">{action.description}</p>
              </div>
            </Link>
          );
        })}
      </div>

      <div className="mt-10">
        <h2 className="mb-4 font-display text-lg font-semibold text-ink-900 dark:text-white">Recent trips</h2>
        <p className="rounded-2xl border border-dashed border-ink-100 p-8 text-center text-sm text-ink-400 dark:border-ink-700">
          Trip history will appear here once the Itinerary module (Phase 2/3) is built.
        </p>
      </div>
    </div>
  );
}
