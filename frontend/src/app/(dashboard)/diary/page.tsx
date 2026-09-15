"use client";

import { useState, useEffect } from "react";
import { BookOpen, Download, AlertCircle } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { useTrips } from "@/features/itinerary/hooks/useTrips";
import { useDiaryEntries, useTripStory, useGenerateTripStory } from "@/features/diary/hooks/useDiary";
import { diaryApi } from "@/features/diary/data/diaryApi";
import { DiaryEntry } from "@/features/diary/components/DiaryEntry";
import { DiaryStats } from "@/features/diary/components/DiaryStats";
import { TripStory } from "@/features/diary/components/TripStory";

export default function TravelDiaryPage() {
  const { data: savedTrips, isLoading: isTripsLoading } = useTrips();
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);

  // Auto-select first trip when loaded
useEffect(() => {
  if (savedTrips && savedTrips.length > 0 && !selectedTripId) {
    const firstTrip = savedTrips[0];

    if (firstTrip) {
      setSelectedTripId(firstTrip.id);
    }
  }
}, [savedTrips, selectedTripId]);

  const activeTrip = savedTrips?.find((t) => t.id === selectedTripId);

  // Queries
  const { data: entries, isLoading: isEntriesLoading } = useDiaryEntries(selectedTripId || '');
  const { data: story, isLoading: isStoryLoading } = useTripStory(selectedTripId || '');
  const generateStoryMutation = useGenerateTripStory(selectedTripId || '');

  const handleExportPDF = () => {
    if (!activeTrip) return;
    diaryApi.exportPdf(activeTrip.id);
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-ink-100 dark:border-ink-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-brand-600" /> Travel Diary & Journal
          </h1>
          <p className="text-sm text-ink-500">
            {activeTrip ? `${activeTrip.destination} (${activeTrip.startDate} to ${activeTrip.endDate})` : "Select a trip to view your diary"}
          </p>
        </div>
        <Button onClick={handleExportPDF} disabled={!activeTrip} className="flex items-center gap-2">
          <Download className="h-4 w-4" /> Export PDF
        </Button>
      </div>

      {/* Select Trip Selector */}
      {isTripsLoading && <p className="text-sm text-ink-400">Loading your trips...</p>}
      
      {savedTrips && savedTrips.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {savedTrips.map((trip) => (
            <button
              key={trip.id}
              onClick={() => setSelectedTripId(trip.id)}
              className={`px-3 py-1.5 rounded-xl text-sm font-medium border transition-colors ${
                selectedTripId === trip.id
                  ? "bg-brand-50 border-brand-500 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300 dark:border-brand-500"
                  : "bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-700 text-ink-600 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800"
              }`}
            >
              {trip.destination}
            </button>
          ))}
        </div>
      )}
      
      {savedTrips && savedTrips.length === 0 && (
        <div className="bg-ink-50 dark:bg-ink-900/50 rounded-2xl p-8 text-center border border-ink-200 dark:border-ink-700 mt-4">
          <AlertCircle className="h-10 w-10 text-ink-400 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-ink-900 dark:text-white mb-2">No trips yet</h3>
          <p className="text-ink-500 max-w-md mx-auto">
            You don't have any saved trips. Head over to the Trip Planner to create your first itinerary and start journaling!
          </p>
        </div>
      )}

      {activeTrip && selectedTripId && (
        <div className="flex flex-col gap-8 mt-2">
          {/* Stats */}
          {entries && entries.length > 0 && (
            <DiaryStats entries={entries} />
          )}

          {/* Entries */}
          <div>
            <h2 className="text-xl font-bold font-display mb-4 text-ink-900 dark:text-white">Daily Entries</h2>
            
            {isEntriesLoading ? (
              <div className="space-y-4">
                {[1, 2].map(i => (
                  <div key={i} className="h-64 bg-ink-50 dark:bg-ink-900 animate-pulse rounded-2xl border border-ink-100 dark:border-ink-700"></div>
                ))}
              </div>
            ) : entries && entries.length > 0 ? (
              <div className="flex flex-col gap-6">
                {entries.map((entry) => {
                  const isToday = new Date(entry.date).toDateString() === new Date().toDateString();
                  return (
                    <DiaryEntry 
                      key={entry.id} 
                      entry={entry} 
                      tripId={selectedTripId}
                      isToday={isToday}
                    />
                  );
                })}
              </div>
            ) : (
              <div className="bg-ink-50 dark:bg-ink-900/50 rounded-2xl p-8 text-center border border-ink-200 dark:border-ink-700">
                <BookOpen className="h-10 w-10 text-ink-400 mx-auto mb-3" />
                <h3 className="text-lg font-bold text-ink-900 dark:text-white mb-2">No entries yet</h3>
                <p className="text-ink-500 max-w-md mx-auto">
                  Diary entries are automatically created for each day of your trip. 
                  Start adding places, notes, and photos!
                </p>
              </div>
            )}
          </div>

          {/* Trip Story */}
          {(!isEntriesLoading && entries && entries.length > 0) && (
            <TripStory 
              tripId={selectedTripId}
              story={story || null}
              onGenerate={() => generateStoryMutation.mutate()}
              isGenerating={generateStoryMutation.isPending || isStoryLoading}
            />
          )}
        </div>
      )}
    </div>
  );
}
