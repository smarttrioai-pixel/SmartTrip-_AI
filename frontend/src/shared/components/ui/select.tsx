"use client";

import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/shared/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: SelectOption[];
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, options, error, id, ...props }, ref) => {
    const selectId = id ?? props.name;
    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={selectId} className="text-sm font-medium text-ink-700 dark:text-ink-100">
          {label}
        </label>
        <select
          id={selectId}
          ref={ref}
          aria-invalid={Boolean(error)}
          className={cn(
            "h-11 rounded-xl border border-ink-100 bg-white px-4 text-sm text-ink-900 outline-none transition-colors focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:border-ink-700 dark:bg-ink-900 dark:text-white",
            error && "border-sunset-500 focus:border-sunset-500 focus:ring-sunset-500",
            className
          )}
          {...props}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {error && <p className="text-xs font-medium text-sunset-600">{error}</p>}
      </div>
    );
  }
);
Select.displayName = "Select";
