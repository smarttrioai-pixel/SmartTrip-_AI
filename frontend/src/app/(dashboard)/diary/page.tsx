"use client";

import { useState } from "react";
import { BookOpen, Download, Calendar, Sparkles, CheckCircle2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { useTrips } from "@/features/itinerary/hooks/useTrips";
import { useGenerateDiary } from "@/features/diary/hooks/useDiary";
import { diaryApi } from "@/features/diary/data/diaryApi";

export default function TravelDiaryPage() {
  const { data: savedTrips, isLoading: isTripsLoading } = useTrips();
  const generateDiaryMutation = useGenerateDiary();

  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);
  const activeTrip = savedTrips?.find((t) => t.id === selectedTripId) ?? savedTrips?.[0];

  const diaryData = generateDiaryMutation.data;

  const handleGenerateDiary = (tripId: string) => {
    setSelectedTripId(tripId);
    generateDiaryMutation.mutate(tripId);
  };

  const handleExportPDF = () => {
    if (!activeTrip) return;
    window.open(diaryApi.getExportPdfUrl(activeTrip.id), "_blank");
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-ink-100 dark:border-ink-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-brand-600" /> Cognitive Travel Diary & Story Journal
          </h1>
          <p className="text-sm text-ink-500">
            {activeTrip ? `${activeTrip.destination} (${activeTrip.startDate} - ${activeTrip.endDate})` : "Select a trip to generate diary"}
          </p>
        </div>
        <Button onClick={handleExportPDF} disabled={!activeTrip} className="flex items-center gap-2">
          <Download className="h-4 w-4" /> Export Trip Summary
        </Button>
      </div>

      {/* Select Trip Selector */}
      {isTripsLoading && <p className="text-sm text-ink-400">Loading your trips...</p>}
      {savedTrips && savedTrips.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {savedTrips.map((trip) => (
            <button
              key={trip.id}
              onClick={() => handleGenerateDiary(trip.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
                activeTrip?.id === trip.id
                  ? "bg-brand-50 border-brand-500 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                  : "border-ink-200 dark:border-ink-700 hover:bg-ink-50 dark:hover:bg-ink-800"
              }`}
            >
              {trip.destination}
            </button>
          ))}
        </div>
      )}
      {savedTrips && savedTrips.length === 0 && (
        <p className="text-sm text-ink-400">No saved trips yet — save a trip from the Trip Planner to generate a diary.</p>
      )}

      {generateDiaryMutation.isPending && <p className="text-sm text-ink-400">Generating your travel diary...</p>}
      {generateDiaryMutation.isError && (
        <p className="text-sm text-sunset-600">{generateDiaryMutation.error.message}</p>
      )}

      {diaryData && (
        <>
          {/* AI Narrative Summary Card */}
          <div className="bg-gradient-to-r from-brand-600 to-indigo-600 text-white p-6 rounded-2xl shadow-md flex flex-col gap-3">
            <div className="flex items-center gap-2 font-semibold text-sm text-brand-100">
              <Sparkles className="h-4 w-4" /> AI Trip Narrative Story
            </div>
            <p className="text-sm md:text-base leading-relaxed opacity-95">{diaryData.ai_narrative_summary}</p>
          </div>

          {/* Expense Summary & Budget Audit */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
              <p className="text-xs font-semibold text-ink-400 uppercase">Estimated Total Cost</p>
              <p className="text-2xl font-bold text-ink-900 dark:text-white mt-1">
                ${diaryData.expense_summary.total_estimated_cost.toFixed(2)} {diaryData.expense_summary.currency}
              </p>
              <p className="text-xs text-emerald-600 font-medium mt-1">
                Status: {diaryData.expense_summary.status}
              </p>
            </div>
            <div className="md:col-span-2 bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
              <p className="text-xs font-semibold text-ink-400 uppercase mb-3">Category Split</p>
              <p className="text-sm text-ink-400">
                {diaryData.expense_summary.note}
              </p>
            </div>
          </div>

          {/* Daily Timeline */}
          <div className="flex flex-col gap-6 mt-2">
            <h2 className="text-lg font-bold text-ink-900 dark:text-white flex items-center gap-2">
              <Calendar className="h-5 w-5 text-brand-600" /> Daily Journal Entries & Memories
            </h2>

            {diaryData.daily_journal.map((day) => (
              <div key={day.day} className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
                <div className="flex items-center justify-between border-b border-ink-100 dark:border-ink-800 pb-3">
                  <div>
                    <span className="text-xs font-bold text-brand-600 dark:text-brand-400 uppercase tracking-wider">
                      Day {day.day} • {day.date}
                    </span>
                    <h3 className="text-base font-bold text-ink-900 dark:text-white mt-0.5">{diaryData.title}</h3>
                  </div>
                </div>

                <p className="text-xs leading-relaxed text-ink-700 dark:text-ink-300">{day.story}</p>

                <div>
                  <p className="text-xs font-semibold text-ink-400 mb-2">Key Highlights</p>
                  <div className="flex flex-wrap gap-2">
                    {day.highlights.map((h, idx) => (
                      <span key={idx} className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300 font-medium">
                        <CheckCircle2 className="h-3 w-3 text-brand-600" /> {h}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
