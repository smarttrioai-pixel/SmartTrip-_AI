import { FEATURE_LABELS } from "@/features/memory/domain/types";

export function FeatureWeightBar({ feature, value }: { feature: string; value: number }) {
  // value is -1..1. Render as a bar from center, filling left (negative) or right (positive).
  const pct = Math.abs(value) * 50;
  const isPositive = value >= 0;

  return (
    <div className="flex items-center gap-3">
      <span className="w-40 shrink-0 text-sm text-ink-700 dark:text-ink-100">
        {FEATURE_LABELS[feature] ?? feature}
      </span>
      <div className="relative h-2 flex-1 rounded-full bg-ink-100 dark:bg-ink-800">
        <div className="absolute left-1/2 top-0 h-full w-px bg-ink-300 dark:bg-ink-600" />
        <div
          className="absolute top-0 h-full rounded-full bg-brand-500"
          style={
            isPositive
              ? { left: "50%", width: `${pct}%` }
              : { right: "50%", width: `${pct}%` }
          }
        />
      </div>
      <span className="w-12 shrink-0 text-right text-xs text-ink-400">{value.toFixed(2)}</span>
    </div>
  );
}
