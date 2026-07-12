import { MessageCircle } from "lucide-react";

export default function ChatPage() {
  return (
    <div className="mx-auto flex min-h-[80vh] max-w-2xl flex-col items-center justify-center gap-3 px-6 text-center">
      <MessageCircle className="h-10 w-10 text-brand-500" aria-hidden="true" />
      <h1 className="font-display text-xl font-semibold text-ink-900 dark:text-white">AI Chat</h1>
      <p className="text-sm text-ink-400">
        The conversational assistant (Module 4) — backend endpoints already exist
        (<code className="rounded bg-ink-100 px-1 py-0.5 text-xs dark:bg-ink-800">POST /chat/messages</code>) —
        the chat UI is scoped for Phase 2.
      </p>
    </div>
  );
}
