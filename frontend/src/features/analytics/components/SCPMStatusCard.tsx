"use client";

import { useState } from "react";
import { Brain, Cpu, RefreshCw, AlertCircle, CheckCircle2, Clock } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { personalizationApi, type SCPMModelStatus } from "@/features/analytics/data/analyticsApi";

interface SCPMStatusCardProps {
  scpmStatus: SCPMModelStatus | undefined;
  onRetrain?: () => void;
}

function MetricPill({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex flex-col gap-0.5 bg-ink-50 dark:bg-ink-800 rounded-xl px-3 py-2">
      <span className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide">{label}</span>
      <span className="text-sm font-bold text-ink-900 dark:text-white">
        {value === null || value === undefined ? "—" : value}
      </span>
    </div>
  );
}

export function SCPMStatusCard({ scpmStatus, onRetrain }: SCPMStatusCardProps) {
  const [training, setTraining] = useState(false);
  const [trainResult, setTrainResult] = useState<string | null>(null);
  const [trainError, setTrainError] = useState<string | null>(null);

  const handleTrain = async () => {
    setTraining(true);
    setTrainResult(null);
    setTrainError(null);
    try {
      const result = await personalizationApi.trainModel();
      setTrainResult(result.message);
      onRetrain?.();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Training request failed.";
      setTrainError(msg);
    } finally {
      setTraining(false);
    }
  };

  // Not yet available (backend might not have returned it yet)
  if (!scpmStatus?.available) {
    return (
      <div className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-3">
        <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
          <Cpu className="h-5 w-5 text-brand-600" /> Personalization Model (SCPM)
        </h2>
        <p className="text-sm text-ink-400">Loading model status…</p>
      </div>
    );
  }

  const isActive = scpmStatus.active === true;
  const sampleCount = scpmStatus.sample_count ?? 0;
  const positiveCount = scpmStatus.positive_count ?? 0;
  const negativeCount = scpmStatus.negative_count ?? 0;
  const accuracy = scpmStatus.accuracy != null ? `${(scpmStatus.accuracy * 100).toFixed(1)}%` : null;
  const baselineAccuracy =
    scpmStatus.baseline_accuracy != null
      ? `${(scpmStatus.baseline_accuracy * 100).toFixed(1)}%`
      : null;
  const f1 = scpmStatus.f1 != null ? scpmStatus.f1.toFixed(3) : null;
  const trainedAt = scpmStatus.trained_at
    ? new Date(scpmStatus.trained_at).toLocaleDateString()
    : null;

  const statusColor = isActive
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-amber-500 dark:text-amber-400";
  const StatusIcon = isActive ? CheckCircle2 : Clock;

  return (
    <div className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
            <Cpu className="h-5 w-5 text-brand-600" /> Personalization Model (SCPM)
          </h2>
          <p className="text-xs text-ink-400 mt-0.5">
            SmartTrip Cognitive Personalization Model — learns your activity preferences from feedback
          </p>
        </div>
        <span className={`flex items-center gap-1.5 text-xs font-semibold ${statusColor}`}>
          <StatusIcon className="h-3.5 w-3.5" />
          {isActive ? "Active" : "Cold-start"}
        </span>
      </div>

      {/* Source */}
      {scpmStatus.personalization_source && (
        <div className="flex items-center gap-2 bg-brand-50 dark:bg-brand-900/20 rounded-xl px-3 py-2">
          <Brain className="h-4 w-4 text-brand-600 shrink-0" />
          <p className="text-xs text-brand-700 dark:text-brand-300 font-medium">
            {scpmStatus.personalization_source}
          </p>
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <MetricPill label="Training Samples" value={sampleCount} />
        <MetricPill label="Accepted" value={positiveCount} />
        <MetricPill label="Rejected" value={negativeCount} />
        {isActive && (
          <>
            <MetricPill label="Accuracy" value={accuracy} />
            <MetricPill label="Baseline" value={baselineAccuracy} />
            <MetricPill label="F1 Score" value={f1} />
          </>
        )}
      </div>

      {/* Cold-start guidance */}
      {!isActive && (
        <div className="flex items-start gap-2 bg-amber-50 dark:bg-amber-900/20 rounded-xl px-3 py-2.5">
          <AlertCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Need ≥10 total feedback events (≥3 likes, ≥3 dislikes) to activate the ML model. Currently
            {" "}{sampleCount} recorded. Accept or reject activities in your itineraries to build the model.
          </p>
        </div>
      )}

      {/* Trained at */}
      {trainedAt && (
        <p className="text-[10px] text-ink-400">Last trained: {trainedAt}</p>
      )}

      {/* Train button */}
      <div className="flex flex-col gap-2 mt-1">
        <Button
          variant="outline"
          size="sm"
          className="self-start flex items-center gap-2"
          onClick={handleTrain}
          disabled={training}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${training ? "animate-spin" : ""}`} />
          {training ? "Training…" : "Train / Retrain Model"}
        </Button>
        {trainResult && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400">{trainResult}</p>
        )}
        {trainError && (
          <p className="text-xs text-red-500">{trainError}</p>
        )}
      </div>
    </div>
  );
}
