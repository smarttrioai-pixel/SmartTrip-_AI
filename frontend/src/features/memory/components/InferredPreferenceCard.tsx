"use client";

import { Sparkles, X } from "lucide-react";

import { useRejectInference } from "@/features/memory/hooks/useMemory";
import type { InferredPreference } from "@/features/memory/domain/types";

export function InferredPreferenceCard({ inference }: { inference: InferredPreference }) {
  const reject = useRejectInference();

  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-ink-100 bg-white p-4 dark:border-ink-700 dark:bg-ink-800">
      <div className="flex items-start gap-3">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" aria-hidden="true" />
        <div>
          <p className="text-sm text-ink-900 dark:text-white">{inference.statement}</p>
          <p className="mt-1 text-xs text-ink-400">
            {Math.round(inference.confidence * 100)}% confidence · from {inference.supportingEventCount} trips
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => reject.mutate(inference.id)}
        disabled={reject.isPending}
        aria-label="This isn't quite right — remove this inference"
        className="shrink-0 rounded-lg p-1.5 text-ink-400 hover:bg-sunset-50 hover:text-sunset-600 disabled:opacity-50"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
