"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  CheckCircle2,
  Circle,
  Loader2,
  MapPin,
  CloudSun,
  Search,
  ShieldCheck,
  Utensils,
  Wallet,
  Route,
  Sparkles,
  ClipboardCheck,
} from "lucide-react";

/**
 * SCIF Generation Progress Panel
 *
 * Displayed while POST /trips/generate is in-flight.
 *
 * HONEST BEHAVIOUR: The backend returns everything in a single response.
 * Individual step completion cannot be tracked from the frontend.
 * Steps animate forward in sequence during loading (realistic timing),
 * then ALL mark ✓ on success, then the panel transitions to the itinerary.
 *
 * We do NOT claim individual steps have "completed" server-side.
 */

interface Step {
  id: string;
  label: string;
  icon: React.ElementType;
  durationMs: number; // approx time before advancing to next step
}

const STEPS: Step[] = [
  { id: "profile", label: "Loading user profile & preferences", icon: Brain, durationMs: 1200 },
  { id: "memory", label: "Retrieving relevant memory", icon: Brain, durationMs: 1600 },
  { id: "context", label: "Gathering destination context", icon: MapPin, durationMs: 1400 },
  { id: "weather", label: "Fetching weather forecast", icon: CloudSun, durationMs: 1800 },
  { id: "places", label: "Finding real places nearby", icon: Search, durationMs: 2200 },
  { id: "verification", label: "Verifying places", icon: ShieldCheck, durationMs: 1600 },
  { id: "restaurants", label: "Finding restaurants", icon: Utensils, durationMs: 1400 },
  { id: "budget", label: "Evaluating budget", icon: Wallet, durationMs: 1200 },
  { id: "route", label: "Optimising route", icon: Route, durationMs: 1200 },
  { id: "reasoning", label: "Cognitive reasoning (Qwen AI)", icon: Sparkles, durationMs: 8000 },
  { id: "verify", label: "Final itinerary verification", icon: ClipboardCheck, durationMs: 2000 },
];

type StepStatus = "pending" | "active" | "done";

interface ScifGenerationProgressProps {
  isVisible: boolean;
  isComplete: boolean;
  error?: string | null;
}

export function ScifGenerationProgress({
  isVisible,
  isComplete,
  error,
}: ScifGenerationProgressProps) {
  const [stepStatuses, setStepStatuses] = useState<Record<string, StepStatus>>(
    () => Object.fromEntries(STEPS.map((s) => [s.id, "pending"]))
  );
  const [activeIndex, setActiveIndex] = useState(-1);
  const [allDone, setAllDone] = useState(false);

  // Advance steps one at a time using cumulative delays
  useEffect(() => {
    if (!isVisible || allDone) return;

    setActiveIndex(0);
    setStepStatuses(Object.fromEntries(STEPS.map((s) => [s.id, "pending"])));

    let cumulative = 0;
    const timers: ReturnType<typeof setTimeout>[] = [];

    STEPS.forEach((step, idx) => {
      // Activate this step
      const activateAt = cumulative;
      timers.push(
        setTimeout(() => {
          setActiveIndex(idx);
          setStepStatuses((prev) => ({ ...prev, [step.id]: "active" }));
        }, activateAt)
      );
      cumulative += step.durationMs;
    });

    return () => timers.forEach(clearTimeout);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible]);

  // When backend responds (success or error), mark all done
  useEffect(() => {
    if (isComplete && !allDone) {
      setAllDone(true);
      setStepStatuses(
        Object.fromEntries(STEPS.map((s) => [s.id, "done"]))
      );
    }
  }, [isComplete, allDone]);

  if (!isVisible) return null;

  return (
    <div className="rounded-2xl border border-brand-100 bg-gradient-to-br from-white to-brand-50/30 p-6 shadow-sm dark:border-brand-900/40 dark:bg-gradient-to-br dark:from-ink-800 dark:to-brand-950/20">
      {/* Header */}
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-100 dark:bg-brand-900/30">
          <Brain className="h-5 w-5 text-brand-600 dark:text-brand-400" />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-brand-600 dark:text-brand-400">
            SCIF Trip Intelligence
          </p>
          <p className="text-sm text-ink-500 dark:text-ink-400">
            {error
              ? "Generation failed"
              : isComplete
              ? "Itinerary ready"
              : "Building your personalised itinerary…"}
          </p>
        </div>
      </div>

      {/* Steps */}
      <div className="flex flex-col gap-2.5">
        {STEPS.map((step, idx) => {
          const status = stepStatuses[step.id] ?? "pending";
          const Icon = step.icon;

          return (
            <div
              key={step.id}
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-all duration-300 ${
                status === "active"
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-900/20 dark:text-brand-300"
                  : status === "done"
                  ? "text-ink-600 dark:text-ink-300"
                  : "text-ink-300 dark:text-ink-600"
              }`}
            >
              {/* Status icon */}
              <div className="shrink-0 w-5 flex justify-center">
                {status === "done" ? (
                  <CheckCircle2 className="h-4 w-4 text-brand-500" />
                ) : status === "active" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
                ) : (
                  <Circle className="h-4 w-4" />
                )}
              </div>

              {/* Step icon */}
              <Icon
                className={`h-3.5 w-3.5 shrink-0 ${
                  status === "active"
                    ? "text-brand-500"
                    : status === "done"
                    ? "text-brand-400"
                    : "text-ink-300 dark:text-ink-600"
                }`}
              />

              {/* Label */}
              <span className={status === "active" ? "font-medium" : ""}>
                {step.label}
              </span>

              {/* Active indicator pulse */}
              {status === "active" && (
                <span className="ml-auto flex h-2 w-2 shrink-0">
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-brand-400 opacity-75 animate-ping" />
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      {!isComplete && !error && (
        <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-ink-100 dark:bg-ink-700">
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-700 ease-out"
            style={{
              width: `${
                activeIndex < 0
                  ? 0
                  : Math.round(((activeIndex + 1) / STEPS.length) * 100)
              }%`,
            }}
          />
        </div>
      )}

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-ink-400 dark:text-ink-600">
        Step order reflects the SCIF pipeline — actual backend timing may vary.
        Cognitive reasoning (Qwen AI) typically takes 20–60 seconds.
      </p>
    </div>
  );
}
