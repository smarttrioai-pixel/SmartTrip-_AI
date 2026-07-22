"use client";

import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/shared/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const inputId = id ?? props.name;
    return (
      <div className="flex flex-col gap-1.5">
  {label && (
    <label
      htmlFor={inputId}
      className="text-sm font-medium text-ink-700 dark:text-ink-100"
    >
      {label}
    </label>
  )}

  <input
    id={inputId}
    ref={ref}
    aria-invalid={Boolean(error)}
    aria-describedby={error ? `${inputId}-error` : undefined}
    className={cn(
      "h-11 rounded-xl border border-ink-100 bg-white px-4 text-sm text-ink-900 outline-none transition-colors placeholder:text-ink-400 focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:border-ink-700 dark:bg-ink-900 dark:text-white",
      error && "border-sunset-500 focus:border-sunset-500 focus:ring-sunset-500",
      className
    )}
    {...props}
  />

  {error && (
    <p id={`${inputId}-error`} className="text-xs font-medium text-sunset-600">
      {error}
    </p>
  )}
</div>
    );
  }
);
Input.displayName = "Input";
