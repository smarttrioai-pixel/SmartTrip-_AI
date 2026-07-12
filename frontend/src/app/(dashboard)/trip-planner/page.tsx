import { Compass } from "lucide-react";

export default function TripPlannerPage() {
  return (
    <div className="mx-auto flex min-h-[80vh] max-w-2xl flex-col items-center justify-center gap-3 px-6 text-center">
      <Compass className="h-10 w-10 text-brand-500" aria-hidden="true" />
      <h1 className="font-display text-xl font-semibold text-ink-900 dark:text-white">AI Trip Planner</h1>
      <p className="text-sm text-ink-400">
        The itinerary generator (Module 5) and its LangGraph multi-agent recommendation pipeline
        (Module 7, 19) are scoped for Phase 2/3 of the roadmap — not built yet.
      </p>
    </div>
  );
}
