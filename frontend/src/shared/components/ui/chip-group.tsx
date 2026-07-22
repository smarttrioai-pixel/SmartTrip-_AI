"use client";

import { cn } from "@/shared/lib/utils";

export interface ChipGroupProps {
  label: string;
  options: string[];
  value: string[];
  onChange: (next: string[]) => void;
}

export function ChipGroup({
  label,
  options,
  value = [],
  onChange,
}: ChipGroupProps) {
  function toggle(option: string) {
   const selected = value ?? [];

onChange(
  selected.includes(option)
    ? selected.filter((v) => v !== option)
    : [...selected, option]
);
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium text-ink-700 dark:text-ink-100">{label}</span>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = (value ?? []).includes(option);
          return (
            <button
              key={option}
              type="button"
              onClick={() => toggle(option)}
              aria-pressed={isSelected}
              className={cn(
                "rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                isSelected
                  ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                  : "border-ink-100 text-ink-700 hover:bg-ink-50 dark:border-ink-700 dark:text-ink-100 dark:hover:bg-ink-800"
              )}
            >
              {option}
            </button>
          );
        })}
      </div>
    </div>
  );
}
