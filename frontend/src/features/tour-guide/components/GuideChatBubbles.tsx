"use client";

import { ChevronRight } from "lucide-react";

import type { GuideMessage, GuidePhase } from "@/features/tour-guide/domain/types";
import { Button } from "@/shared/components/ui/button";

interface GuideChatBubblesProps {
  messages: GuideMessage[];
  phase: GuidePhase;
  onStartWalkthrough: () => void;
  onShowItinerary: () => void;
  onNextActivity: () => void;
  showFullItinerary: boolean;
  hasActivities: boolean;
}

export function GuideChatBubbles({
  messages,
  phase,
  onStartWalkthrough,
  onShowItinerary,
  onNextActivity,
  showFullItinerary,
  hasActivities,
}: GuideChatBubblesProps) {
  const visibleMessages = messages.slice(-4);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 max-h-[320px] overflow-y-auto pr-1">
        {visibleMessages.map((msg) => (
          <div
            key={msg.id}
            className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              msg.role === "guide"
                ? "bg-white border border-ink-100 text-ink-800 dark:bg-ink-800 dark:border-ink-700 dark:text-ink-100"
                : "bg-brand-50 border border-brand-100 text-brand-900 dark:bg-brand-900/30 dark:border-brand-800 dark:text-brand-100 ml-4"
            }`}
          >
            {msg.text}
          </div>
        ))}
      </div>

      {phase === "welcome" && (
        <div className="flex flex-col gap-2">
          <Button onClick={onStartWalkthrough} className="w-full justify-center">
            Yes, let&apos;s start
          </Button>
          <Button variant="outline" onClick={onShowItinerary} className="w-full justify-center">
            Show full itinerary
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}

      {phase === "walkthrough" && hasActivities && (
        <Button variant="outline" onClick={onNextActivity} className="w-full">
          Next stop
          <ChevronRight className="h-4 w-4" />
        </Button>
      )}

      {phase === "finished" && (
        <p className="text-xs text-ink-400 dark:text-ink-500 text-center">
          Day 1 walkthrough complete. Use the camera or ask a question below.
        </p>
      )}

      {showFullItinerary && (
        <p className="text-xs font-medium text-brand-600 dark:text-brand-400 text-center">
          Full itinerary shown on the right →
        </p>
      )}
    </div>
  );
}
