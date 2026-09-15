"use client";

import { useState } from "react";
import { Mic, Send } from "lucide-react";

import { Button } from "@/shared/components/ui/button";

const SUGGESTIONS = ["Local food", "History", "Safety", "Best photo spots"];

interface GuideInputBarProps {
  onAsk: (question: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

export function GuideInputBar({ onAsk, isLoading, disabled }: GuideInputBarProps) {
  const [question, setQuestion] = useState("");

  const submit = () => {
    const trimmed = question.trim();
    if (!trimmed || disabled) return;
    onAsk(trimmed);
    setQuestion("");
  };

  return (
    <div className="rounded-2xl border border-ink-100 bg-white p-4 dark:border-ink-700 dark:bg-ink-900">
      <div className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Type your question…"
          disabled={disabled || isLoading}
          className="flex-1 h-10 rounded-xl border border-ink-100 bg-ink-50 px-4 text-sm text-ink-900 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:border-ink-700 dark:bg-ink-800 dark:text-white placeholder:text-ink-400"
        />
        <Button
          size="sm"
          onClick={submit}
          isLoading={isLoading}
          disabled={disabled || !question.trim()}
          aria-label="Send question"
        >
          <Send className="h-4 w-4" />
        </Button>
        <button
          type="button"
          disabled={disabled}
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-ink-100 text-ink-400 hover:bg-ink-50 dark:border-ink-700 dark:hover:bg-ink-800 disabled:opacity-40"
          aria-label="Voice input (coming soon)"
          title="Voice input uses browser speech in a future update"
        >
          <Mic className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((chip) => (
          <button
            key={chip}
            type="button"
            disabled={disabled || isLoading}
            onClick={() => onAsk(`Tell me about ${chip.toLowerCase()} for this trip`)}
            className="rounded-lg bg-ink-50 px-2.5 py-1 text-[11px] font-medium text-ink-600 hover:bg-brand-50 hover:text-brand-700 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-brand-900/30 dark:hover:text-brand-300 disabled:opacity-40"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  );
}
