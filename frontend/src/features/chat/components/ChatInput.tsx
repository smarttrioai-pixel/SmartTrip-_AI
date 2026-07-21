"use client";

import { Send } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { Button } from "@/shared/components/ui/button";

export function ChatInput({ onSend, isSending }: { onSend: (message: string) => void; isSending: boolean }) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || isSending) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex items-end gap-2 border-t border-ink-100 bg-white p-4 dark:border-ink-700 dark:bg-ink-900">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about destinations, packing, visas, local customs…"
        rows={1}
        className="max-h-32 flex-1 resize-none rounded-xl border border-ink-100 bg-white px-4 py-2.5 text-sm text-ink-900 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:border-ink-700 dark:bg-ink-800 dark:text-white"
      />
      <Button type="button" size="default" onClick={submit} isLoading={isSending} aria-label="Send message">
        <Send className="h-4 w-4" />
      </Button>
    </div>
  );
}
