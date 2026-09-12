"use client";

import { useState } from "react";
import {
  Brain,
  CloudSun,
  Wallet,
  MapPin,
  ShieldCheck,
  Cpu,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertCircle,
  Info,
  Zap,
} from "lucide-react";

import type { CognitiveTrace } from "@/features/itinerary/domain/scif-types";

interface ScifIntelligencePanelProps {
  cognitiveTrace: CognitiveTrace | null;
}

/**
 * Displays the SCIF cognitive pipeline trace returned by the backend.
 * Only renders sections for which the backend actually returned data.
 * No values are hardcoded or fabricated.
 */
export function ScifIntelligencePanel({
  cognitiveTrace,
}: ScifIntelligencePanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showAllStages, setShowAllStages] = useState(false);
  const [showAllConstraints, setShowAllConstraints] = useState(false);

  if (!cognitiveTrace) return null;

  const pipeline = cognitiveTrace.scif_pipeline;

  // Determine whether we have new-format or old-format trace
  const hasNewFormat = !!pipeline;
  const hasOldFormat = !pipeline && cognitiveTrace.scif_decisions !== undefined;

  if (!hasNewFormat && !hasOldFormat) return null;

  const allConstraints = [
    ...(pipeline?.weather_constraints ?? []),
    ...(pipeline?.scif_constraints ?? []),
  ];

  const shownConstraints = showAllConstraints
    ? allConstraints
    : allConstraints.slice(0, 4);

  const agents = pipeline?.agent_outputs ?? [];
  const stages = pipeline?.pipeline_stages ?? [];
  const shownStages = showAllStages ? stages : stages.slice(0, 6);

  const budget = pipeline?.budget;
  const memory = pipeline?.memory;
  const profile = pipeline?.profile;
  const weather = pipeline?.weather;

  // Old-format decisions (pre-SCIF orchestrator)
  const decisions = cognitiveTrace.scif_decisions ?? [];

  return (
    <div className="rounded-2xl border border-brand-100 bg-gradient-to-br from-white to-brand-50/20 dark:border-brand-900/30 dark:from-ink-800 dark:to-ink-800 overflow-hidden">
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 hover:bg-brand-50/50 dark:hover:bg-brand-900/10 transition-colors"
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-brand-100 dark:bg-brand-900/40 shrink-0">
            <Brain className="h-4 w-4 text-brand-600 dark:text-brand-400" />
          </div>
          <div className="text-left">
            <p className="text-sm font-semibold text-ink-900 dark:text-white">
              SCIF Intelligence Report
            </p>
            <p className="text-xs text-ink-400 dark:text-ink-500">
              {hasNewFormat
                ? `${agents.length} agent${agents.length !== 1 ? "s" : ""} · ${allConstraints.length} constraint${allConstraints.length !== 1 ? "s" : ""} · ${stages.length} pipeline stage${stages.length !== 1 ? "s" : ""}`
                : `${decisions.length} SCIF decision${decisions.length !== 1 ? "s" : ""}`}
            </p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-ink-400 shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 text-ink-400 shrink-0" />
        )}
      </button>

      {isExpanded && (
        <div className="border-t border-brand-100 dark:border-brand-900/30 px-5 py-5 flex flex-col gap-6">

          {/* ── Memory ─────────────────────────────────── */}
          {memory && (
            <Section icon={Brain} title="Memory Used" color="purple">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Stat label="Items retrieved" value={memory.items_retrieved} />
                <Stat label="Source" value={memory.source} />
              </div>
              {memory.summary && (
                <p className="mt-2 rounded-lg bg-purple-50/60 px-3 py-2 text-xs text-purple-800 dark:bg-purple-900/20 dark:text-purple-300 italic">
                  &ldquo;{memory.summary}&rdquo;
                </p>
              )}
            </Section>
          )}

          {/* ── Profile ─────────────────────────────────── */}
          {profile && (
            <Section icon={Info} title="User Profile Applied" color="brand">
              <div className="flex flex-wrap gap-2 text-xs">
                {profile.food_preference && profile.food_preference !== "no_preference" && (
                  <Badge color="green">{profile.food_preference}</Badge>
                )}
                {profile.travel_style && (
                  <Badge color="blue">{profile.travel_style} style</Badge>
                )}
                {(profile.interests ?? []).slice(0, 5).map((i) => (
                  <Badge key={i} color="gray">{i}</Badge>
                ))}
              </div>
            </Section>
          )}

          {/* ── Budget ─────────────────────────────────── */}
          {budget && (budget.tier || budget.daily_budget != null) && (
            <Section icon={Wallet} title="Budget Analysis" color="amber">
              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                {budget.tier && (
                  <Stat
                    label="Tier"
                    value={
                      budget.tier === "budget"
                        ? "Budget"
                        : budget.tier === "luxury"
                        ? "Luxury"
                        : "Mid-range"
                    }
                  />
                )}
                {budget.daily_budget != null && (
                  <Stat
                    label="Daily budget"
                    value={`${budget.currency ?? ""} ${budget.daily_budget.toLocaleString()}`}
                  />
                )}
                {budget.meal_budget_per_day != null && (
                  <Stat
                    label="Meals/day"
                    value={`${budget.currency ?? ""} ${budget.meal_budget_per_day.toLocaleString()}`}
                  />
                )}
                {budget.activity_budget_per_day != null && (
                  <Stat
                    label="Activities/day"
                    value={`${budget.currency ?? ""} ${budget.activity_budget_per_day.toLocaleString()}`}
                  />
                )}
              </div>
            </Section>
          )}

          {/* ── Weather ─────────────────────────────────── */}
          {weather && (
            <Section icon={CloudSun} title="Weather Intelligence" color="sky">
              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                {Object.entries(weather.weather_days ?? {}).slice(0, 4).map(([date, day]) => (
                  <div
                    key={date}
                    className="rounded-lg bg-sky-50 px-3 py-2 dark:bg-sky-900/20"
                  >
                    <p className="text-[10px] font-medium text-sky-600 dark:text-sky-400 mb-0.5">{date}</p>
                    <p className="text-xs font-semibold text-ink-800 dark:text-white">
                      {day.condition ?? "—"}
                    </p>
                    {day.temperature_max != null && (
                      <p className="text-[10px] text-ink-500 dark:text-ink-400">
                        {day.temperature_min?.toFixed(0)}°–{day.temperature_max?.toFixed(0)}°C
                      </p>
                    )}
                    {day.rain_probability != null && (
                      <p className="text-[10px] text-ink-500 dark:text-ink-400">
                        Rain: {Math.round(day.rain_probability * 100)}%
                      </p>
                    )}
                    <span
                      className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[9px] font-semibold ${
                        day.is_suitable_outdoor
                          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400"
                      }`}
                    >
                      {day.is_suitable_outdoor ? "Outdoor OK" : "Avoid outdoor"}
                    </span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* ── Planning Constraints ──────────────────────── */}
          {allConstraints.length > 0 && (
            <Section icon={Zap} title="Planning Constraints Applied to Qwen" color="amber">
              <ul className="flex flex-col gap-1.5">
                {shownConstraints.map((c, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 rounded-lg bg-amber-50/70 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/20 dark:text-amber-300"
                  >
                    <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
                    {c}
                  </li>
                ))}
              </ul>
              {allConstraints.length > 4 && (
                <button
                  type="button"
                  onClick={() => setShowAllConstraints((v) => !v)}
                  className="mt-2 text-xs font-medium text-brand-600 hover:underline"
                >
                  {showAllConstraints
                    ? "Show less"
                    : `Show ${allConstraints.length - 4} more constraints`}
                </button>
              )}
            </Section>
          )}

          {/* ── Agent Contributions ────────────────────────── */}
          {agents.length > 0 && (
            <Section icon={Cpu} title="Agent Contributions" color="brand">
              <div className="flex flex-col gap-3">
                {agents.map((agent) => (
                  <div
                    key={agent.agent}
                    className="rounded-xl border border-ink-100 bg-white p-3 dark:border-ink-700 dark:bg-ink-900"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {agent.status === "ok" ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                        ) : (
                          <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                        )}
                        <span className="text-sm font-medium text-ink-900 dark:text-white">
                          {agent.agent}
                        </span>
                      </div>
                      <span
                        className={`text-[10px] font-semibold rounded px-1.5 py-0.5 ${
                          agent.status === "ok"
                            ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                            : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
                        }`}
                      >
                        {agent.status.toUpperCase()}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs text-ink-500 dark:text-ink-400">
                      <span className="font-medium text-ink-700 dark:text-ink-300">Source:</span>{" "}
                      {agent.data_source}
                    </p>
                    {agent.contribution && (
                      <p className="mt-0.5 text-xs text-ink-500 dark:text-ink-400">
                        <span className="font-medium text-ink-700 dark:text-ink-300">
                          Contribution:
                        </span>{" "}
                        {agent.contribution}
                      </p>
                    )}
                    {agent.items_returned > 0 && (
                      <p className="mt-0.5 text-xs text-ink-500 dark:text-ink-400">
                        {agent.items_returned} item{agent.items_returned !== 1 ? "s" : ""} returned
                        {agent.latency_ms > 0 ? ` · ${agent.latency_ms.toFixed(0)}ms` : ""}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* ── Pipeline Stages ────────────────────────────── */}
          {stages.length > 0 && (
            <Section icon={MapPin} title="Pipeline Stages" color="gray">
              <div className="flex flex-col gap-1.5">
                {shownStages.map((stage, i) => (
                  <div
                    key={stage.stage}
                    className="flex items-center gap-3 rounded-lg px-3 py-2 bg-ink-50/80 dark:bg-ink-900/50 text-xs"
                  >
                    <span className="w-5 text-center font-mono text-ink-400 dark:text-ink-600 shrink-0">
                      {i + 1}
                    </span>
                    {stage.status === "ok" ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                    ) : stage.status === "error" ? (
                      <AlertCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                    ) : (
                      <AlertCircle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <span className="font-medium text-ink-800 dark:text-ink-200">
                        {stage.stage}
                      </span>
                      <span className="ml-1 text-ink-400 dark:text-ink-500">
                        · {stage.component}
                      </span>
                    </div>
                    {stage.latency_ms > 0 && (
                      <span className="text-ink-400 dark:text-ink-600 shrink-0 font-mono">
                        {stage.latency_ms.toFixed(0)}ms
                      </span>
                    )}
                  </div>
                ))}
              </div>
              {stages.length > 6 && (
                <button
                  type="button"
                  onClick={() => setShowAllStages((v) => !v)}
                  className="mt-2 text-xs font-medium text-brand-600 hover:underline"
                >
                  {showAllStages
                    ? "Show less"
                    : `Show ${stages.length - 6} more stages`}
                </button>
              )}
            </Section>
          )}

          {/* ── Old-format SCIF Decisions ─────────────────── */}
          {!hasNewFormat && decisions.length > 0 && (
            <Section icon={ShieldCheck} title="SCIF Decisions" color="brand">
              <div className="flex flex-col gap-2">
                {decisions.map((d, i) => (
                  <div
                    key={i}
                    className="rounded-xl border border-ink-100 bg-white p-3 dark:border-ink-700 dark:bg-ink-900 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-ink-900 dark:text-white">{d.place}</span>
                      <Badge
                        color={
                          d.decision === "approve"
                            ? "green"
                            : d.decision === "reject"
                            ? "red"
                            : "amber"
                        }
                      >
                        {d.decision}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-ink-500 dark:text-ink-400">{d.reason}</p>
                    {d.suggested_time && (
                      <p className="mt-0.5 text-xs text-brand-600 dark:text-brand-400">
                        Suggested time: {d.suggested_time}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ────────────────────────────────────────────────────────

type ColorToken = "brand" | "purple" | "amber" | "sky" | "gray" | "green";

function Section({
  icon: Icon,
  title,
  color,
  children,
}: {
  icon: React.ElementType;
  title: string;
  color: ColorToken;
  children: React.ReactNode;
}) {
  const bgMap: Record<ColorToken, string> = {
    brand: "bg-brand-100 dark:bg-brand-900/40",
    purple: "bg-purple-100 dark:bg-purple-900/40",
    amber: "bg-amber-100 dark:bg-amber-900/40",
    sky: "bg-sky-100 dark:bg-sky-900/40",
    gray: "bg-ink-100 dark:bg-ink-700/40",
    green: "bg-green-100 dark:bg-green-900/40",
  };
  const iconMap: Record<ColorToken, string> = {
    brand: "text-brand-600 dark:text-brand-400",
    purple: "text-purple-600 dark:text-purple-400",
    amber: "text-amber-600 dark:text-amber-400",
    sky: "text-sky-600 dark:text-sky-400",
    gray: "text-ink-500 dark:text-ink-400",
    green: "text-green-600 dark:text-green-400",
  };

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <div className={`flex h-6 w-6 items-center justify-center rounded-lg ${bgMap[color]}`}>
          <Icon className={`h-3.5 w-3.5 ${iconMap[color]}`} />
        </div>
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-500 dark:text-ink-400">
          {title}
        </p>
      </div>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-ink-50 px-3 py-2 dark:bg-ink-900/50">
      <p className="text-[10px] text-ink-400 dark:text-ink-500 mb-0.5">{label}</p>
      <p className="text-sm font-semibold text-ink-800 dark:text-white">{value}</p>
    </div>
  );
}

type BadgeColor = "green" | "red" | "amber" | "blue" | "gray";

function Badge({
  children,
  color = "gray",
}: {
  children: React.ReactNode;
  color?: BadgeColor;
}) {
  const colorMap: Record<BadgeColor, string> = {
    green: "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400",
    red: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
    blue: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    gray: "bg-ink-50 text-ink-600 dark:bg-ink-700 dark:text-ink-300",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold ${colorMap[color]}`}
    >
      {children}
    </span>
  );
}
