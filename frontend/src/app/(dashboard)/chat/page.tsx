"use client";

import { useState } from "react";

import { ChatSidebar } from "@/features/chat/components/ChatSidebar";
import { ChatWindow } from "@/features/chat/components/ChatWindow";

export default function ChatPage() {
  const [activeChatId, setActiveChatId] = useState<string | null>(null);

  return (
    <div className="flex h-screen">
      <ChatSidebar
        activeChatId={activeChatId}
        onSelectChat={setActiveChatId}
        onNewChat={() => setActiveChatId(null)}
      />
      <div className="flex-1">
        <ChatWindow activeChatId={activeChatId} onChatCreated={setActiveChatId} />
      </div>
    </div>
  );
}
