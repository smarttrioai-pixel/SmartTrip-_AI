import { useState } from "react";
import { MessageSquare, Send, AlertTriangle } from "lucide-react";
import { useModifyItinerary } from "@/features/itinerary/hooks/useItineraryActions";
import type { ModifyItineraryResponse } from "@/features/itinerary/domain/types";
import { Button } from "@/shared/components/ui/button";

export interface PlannerChatProps {
  tripId: string;
  onModification: (result: ModifyItineraryResponse) => void;
}

export function PlannerChat({ tripId, onModification }: PlannerChatProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState("");
  const modifyMutation = useModifyItinerary(tripId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || modifyMutation.isPending) return;

    modifyMutation.mutate(
      { user_message: message },
      {
        onSuccess: (result) => {
          onModification(result);
          setMessage("");
        },
      }
    );
  };

  if (!isOpen) {
    return (
      <div className="fixed bottom-6 right-6 z-40">
        <Button
          size="lg"
          className="rounded-full h-14 w-14 shadow-xl"
          onClick={() => setIsOpen(true)}
        >
          <MessageSquare className="h-6 w-6" />
        </Button>
      </div>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-40 w-full max-w-sm rounded-2xl bg-white shadow-2xl border border-ink-200 dark:bg-ink-900 dark:border-ink-700 overflow-hidden">
      <div className="bg-brand-600 px-4 py-3 flex items-center justify-between">
        <h3 className="text-white font-medium flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          Modify Itinerary
        </h3>
        <button
          onClick={() => setIsOpen(false)}
          className="text-brand-100 hover:text-white"
        >
          ✕
        </button>
      </div>

      <div className="p-4 bg-ink-50 dark:bg-ink-900/50">
        {modifyMutation.isError && (
          <div className="mb-3 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400 border border-red-100 dark:border-red-900">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <p>Something went wrong. Please try again.</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder='e.g., "Remove the museum and add a cafe instead" or "Make Day 2 cheaper"'
            className="w-full resize-none rounded-xl border border-ink-200 bg-white p-3 text-sm text-ink-900 placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 dark:border-ink-700 dark:bg-ink-950 dark:text-white"
            rows={3}
            disabled={modifyMutation.isPending}
          />
          <Button
            type="submit"
            disabled={!message.trim() || modifyMutation.isPending}
            isLoading={modifyMutation.isPending}
            className="w-full"
          >
            {modifyMutation.isPending ? (
              "Modifying..."
            ) : (
              <>
                <Send className="mr-2 h-4 w-4" />
                Send Request
              </>
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
