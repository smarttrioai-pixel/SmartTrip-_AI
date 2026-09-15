import React from 'react';
import { WRITING_STYLES, type WritingStyle } from '../domain/types';

interface WritingStylePickerProps {
  value: WritingStyle;
  onChange: (style: WritingStyle) => void;
}

export function WritingStylePicker({ value, onChange }: WritingStylePickerProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      {WRITING_STYLES.map((style) => (
        <button
          key={style.value}
          onClick={() => onChange(style.value)}
          className={`flex flex-col items-start p-3 rounded-xl border text-left transition-colors ${
            value === style.value
              ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20 dark:border-brand-400'
              : 'border-ink-200 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-800'
          }`}
        >
          <span className={`text-sm font-semibold ${value === style.value ? 'text-brand-700 dark:text-brand-300' : 'text-ink-900 dark:text-white'}`}>
            {style.label}
          </span>
          <span className={`text-xs mt-1 ${value === style.value ? 'text-brand-600 dark:text-brand-400' : 'text-ink-500 dark:text-ink-400'}`}>
            {style.description}
          </span>
        </button>
      ))}
    </div>
  );
}
