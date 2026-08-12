"use client";

import { Bot } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useChatHistory, useSendMessage } from "@/features/chat/hooks/useChat";
import type { ChatMessage } from "@/features/chat/domain/types";
import { ChatInput } from "@/features/chat/components/ChatInput";
import { MessageBubble } from "@/features/chat/components/MessageBubble";

const SUGGESTIONS = [
  "What should I pack for a 5-day trip to Tokyo in October?",
  "What's the best way to get from Rome's airport to the city center?",
  "Any visa requirements for a US passport holder visiting Vietnam?",
];

export function ChatWindow({
  activeChatId,
  onChatCreated,
}: {
  activeChatId: string | null;
  onChatCreated: (chatId: string) => void;
}) {
  const { data: history, isLoading: historyLoading } = useChatHistory(activeChatId);
  const sendMessage = useSendMessage();
  const [optimisticMessages, setOptimisticMessages] = useState<ChatMessage[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Reset local optimistic state whenever the active conversation changes.
  useEffect(() => {
    setOptimisticMessages([]);
  }, [activeChatId]);

  const messages: ChatMessage[] = [...(history ?? []), ...optimisticMessages];

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  function handleSend(content: string) {
    setOptimisticMessages((prev) => [...prev, { role: "user", content }]);
    sendMessage.mutate(
      { message: content, chatId: activeChatId },
      {
        onSuccess: ({ chatId, reply }) => {
          setOptimisticMessages((prev) => [...prev, { role: "assistant", content: reply }]);
          if (!activeChatId) onChatCreated(chatId);
        },
        onError: () => {
          // Leave the user's message visible but drop the failed send attempt
          // from pending state so retry isn't blocked; the error renders below.
        },
      }
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-6">
        {messages.length === 0 && !historyLoading && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-300">
              <Bot className="h-6 w-6" />
            </div>
            <div>
              <p className="font-medium text-ink-900 dark:text-white">Ask your AI travel guide anything</p>
              <p className="mt-1 text-sm text-ink-400">Trip ideas, packing, visas, local customs, and more.</p>
            </div>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSend(s)}
                  className="rounded-xl border border-ink-100 px-4 py-2 text-left text-sm text-ink-700 hover:bg-ink-50 dark:border-ink-700 dark:text-ink-100 dark:hover:bg-ink-800"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, i) => (
          <MessageBubble key={i} message={message} />
        ))}

        {sendMessage.isPending && (
          <div className="flex items-center gap-2 text-sm text-ink-400">
            <span className="h-2 w-2 animate-bounce rounded-full bg-ink-400 [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-ink-400 [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-ink-400" />
          </div>
        )}

        {sendMessage.isError && (
          <p role="alert" className="text-sm font-medium text-sunset-600">
            {sendMessage.error.message}
          </p>
        )}
      </div>

      <ChatInput onSend={handleSend} isSending={sendMessage.isPending} />
    </div>
  );
}
