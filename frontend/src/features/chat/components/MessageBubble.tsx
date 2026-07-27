import { Bot, User } from "lucide-react";

import { cn } from "@/shared/lib/utils";
import type { ChatMessage } from "@/features/chat/domain/types";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-ink-100 text-ink-700 dark:bg-ink-800 dark:text-ink-100" : "bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={cn(
          "max-w-[75%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-brand-500 text-white"
            : "bg-white text-ink-900 shadow-card dark:bg-ink-800 dark:text-white"
        )}
      >
        {message.content}
      </div>
    </div>
  );
}
