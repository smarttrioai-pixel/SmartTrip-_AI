"use client";

import { MessageSquarePlus } from "lucide-react";

import { useChatList } from "@/features/chat/hooks/useChat";
import { cn } from "@/shared/lib/utils";

export function ChatSidebar({
  activeChatId,
  onSelectChat,
  onNewChat,
}: {
  activeChatId: string | null;
  onSelectChat: (chatId: string) => void;
  onNewChat: () => void;
}) {
  const { data: chats, isLoading } = useChatList();

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-100 bg-white dark:border-ink-700 dark:bg-ink-900 md:flex">
      <div className="p-4">
        <button
          onClick={onNewChat}
          className="flex w-full items-center gap-2 rounded-xl border border-ink-100 px-3 py-2.5 text-sm font-medium text-ink-700 hover:bg-ink-50 dark:border-ink-700 dark:text-ink-100 dark:hover:bg-ink-800"
        >
          <MessageSquarePlus className="h-4 w-4" />
          New conversation
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {isLoading && <p className="px-2 text-sm text-ink-400">Loading…</p>}
        {chats?.length === 0 && <p className="px-2 text-sm text-ink-400">No conversations yet.</p>}
        {chats?.map((chat) => (
          <button
            key={chat.id}
            onClick={() => onSelectChat(chat.id)}
            className={cn(
              "block w-full truncate rounded-lg px-3 py-2 text-left text-sm",
              chat.id === activeChatId
                ? "bg-brand-50 font-medium text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                : "text-ink-700 hover:bg-ink-50 dark:text-ink-100 dark:hover:bg-ink-800"
            )}
          >
            {chat.title}
          </button>
        ))}
      </div>
    </aside>
  );
}
