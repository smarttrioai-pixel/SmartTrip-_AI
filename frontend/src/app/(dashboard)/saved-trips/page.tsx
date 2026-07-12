import { MapPinned } from "lucide-react";

export default function SavedTripsPage() {
  return (
    <div className="mx-auto flex min-h-[80vh] max-w-2xl flex-col items-center justify-center gap-3 px-6 text-center">
      <MapPinned className="h-10 w-10 text-brand-500" aria-hidden="true" />
      <h1 className="font-display text-xl font-semibold text-ink-900 dark:text-white">Saved Trips</h1>
      <p className="text-sm text-ink-400">
        Trip list + the MapLibre/OpenStreetMap map view (Module 13) are scoped for Phase 4 of the
        roadmap — not built yet.
      </p>
    </div>
  );
}
