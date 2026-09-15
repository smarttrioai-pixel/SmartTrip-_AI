import { X } from "lucide-react";
import type { ActivityAlternative } from "@/features/itinerary/domain/types";
import { AlternativeCard } from "./AlternativeCard";
import { Button } from "@/shared/components/ui/button";

export interface AlternativePanelProps {
  isOpen: boolean;
  activityTitle: string;
  alternatives: ActivityAlternative[];
  isLoading: boolean;
  onReplace: (alt: ActivityAlternative) => void;
  onClose: () => void;
}

export function AlternativePanel({
  isOpen,
  activityTitle,
  alternatives,
  isLoading,
  onReplace,
  onClose,
}: AlternativePanelProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-2xl dark:bg-ink-900 border-l border-ink-200 dark:border-ink-800 transition-transform duration-300">
      <div className="flex items-center justify-between border-b border-ink-100 p-4 dark:border-ink-800">
        <h3 className="font-semibold text-ink-900 dark:text-white">
          Alternatives to {activityTitle}
        </h3>
        <button
          onClick={onClose}
          className="rounded-full p-1.5 text-ink-500 hover:bg-ink-100 dark:hover:bg-ink-800"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse flex flex-col gap-2 border border-ink-200 rounded-xl p-4">
                <div className="h-4 bg-ink-200 rounded w-3/4"></div>
                <div className="h-3 bg-ink-200 rounded w-1/2"></div>
                <div className="h-16 bg-ink-200 rounded w-full mt-2"></div>
              </div>
            ))}
          </div>
        ) : alternatives.length > 0 ? (
          alternatives.map((alt, idx) => (
            <AlternativeCard
              key={idx}
              alternative={alt}
              onReplace={() => onReplace(alt)}
            />
          ))
        ) : (
          <div className="text-center text-ink-500 mt-10">
            No alternatives found.
          </div>
        )}
      </div>

      <div className="border-t border-ink-100 p-4 dark:border-ink-800">
        <Button variant="outline" className="w-full" onClick={onClose}>
          Keep Current
        </Button>
      </div>
    </div>
  );
}
