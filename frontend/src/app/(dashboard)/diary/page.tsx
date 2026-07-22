"use client";

import { useState } from "react";
import { BookOpen, Download, Calendar, DollarSign, Sparkles, Image as ImageIcon, CheckCircle2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";

export default function TravelDiaryPage() {
  const [isExporting, setIsExporting] = useState(false);

  const diary = {
    trip_title: "Romantic Summer Journey in Paris",
    date_range: "July 20, 2026 - July 25, 2026",
    ai_story:
      "A magical five-day adventure across the heart of Paris. From sunrise coffee near Montmartre to golden hour moments at the Seine waterfront, every day offered unforgettable art, culinary perfection, and historic charm.",
    expenses: {
      total_spent: 1240.0,
      budget: 1500.0,
      currency: "USD",
      breakdown: [
        { category: "Accommodation", amount: 560.0 },
        { category: "Dining & Cafés", amount: 380.0 },
        { category: "Attractions & Museums", amount: 180.0 },
        { category: "Transport", amount: 120.0 },
      ],
    },
    days: [
      {
        day: 1,
        date: "July 20, 2026",
        title: "Arrival & Montmartre Discovery",
        story:
          "Arrived in Paris in high spirits. Checked into boutique hotel in Montmartre, followed by a evening walk up to Sacré-Cœur for a sweeping view of Paris.",
        highlights: ["Boutique hotel check-in", "Sacré-Cœur panoramic view", "French onion soup dinner"],
        photos: ["https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=600&auto=format&fit=crop"],
      },
      {
        day: 2,
        date: "July 21, 2026",
        title: "Louvre Masterpieces & Seine Cruise",
        story:
          "Spent the morning immersed in art at the Louvre. Afternoon pastry tasting at Saint-Germain followed by a romantic sunset cruise along the Seine.",
        highlights: ["Mona Lisa & Venus de Milo", "Artisan macarons tasting", "Evening boat cruise"],
        photos: ["https://images.unsplash.com/photo-1499856871958-5b9627545d1a?w=600&auto=format&fit=crop"],
      },
    ],
  };

  const handleDownloadPDF = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      window.open("http://localhost:8000/api/v1/diary/export-pdf/trip_123", "_blank");
    }, 800);
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-ink-100 dark:border-ink-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
            <BookOpen className="h-6 w-6 text-brand-600" /> Cognitive Travel Diary & Story Journal
          </h1>
          <p className="text-sm text-ink-500">{diary.trip_title} • {diary.date_range}</p>
        </div>
        <Button onClick={handleDownloadPDF} disabled={isExporting} className="flex items-center gap-2">
          <Download className="h-4 w-4" /> {isExporting ? "Generating PDF..." : "Export Shareable PDF"}
        </Button>
      </div>

      {/* AI Narrative Summary Card */}
      <div className="bg-gradient-to-r from-brand-600 to-indigo-600 text-white p-6 rounded-2xl shadow-md flex flex-col gap-3">
        <div className="flex items-center gap-2 font-semibold text-sm text-brand-100">
          <Sparkles className="h-4 w-4" /> AI Trip Narrative Summary
        </div>
        <p className="text-sm md:text-base leading-relaxed opacity-95">{diary.ai_story}</p>
      </div>

      {/* Expense Summary & Budget Audit */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase">Total Spent</p>
          <p className="text-2xl font-bold text-ink-900 dark:text-white mt-1">
            ${diary.expenses.total_spent.toFixed(2)}
          </p>
          <p className="text-xs text-emerald-600 font-medium mt-1">
            Under Budget by ${(diary.expenses.budget - diary.expenses.total_spent).toFixed(2)}
          </p>
        </div>
        <div className="md:col-span-2 bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700">
          <p className="text-xs font-semibold text-ink-400 uppercase mb-3">Category Breakdown</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {diary.expenses.breakdown.map((item, idx) => (
              <div key={idx} className="p-2.5 rounded-xl bg-ink-50 dark:bg-ink-800">
                <p className="text-[11px] text-ink-400">{item.category}</p>
                <p className="text-sm font-bold text-ink-900 dark:text-white">${item.amount}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Daily Timeline */}
      <div className="flex flex-col gap-6 mt-2">
        <h2 className="text-lg font-bold text-ink-900 dark:text-white flex items-center gap-2">
          <Calendar className="h-5 w-5 text-brand-600" /> Daily Journal Entries & Memories
        </h2>

        {diary.days.map((day) => (
          <div key={day.day} className="bg-white dark:bg-ink-900 p-6 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-ink-100 dark:border-ink-800 pb-3">
              <div>
                <span className="text-xs font-bold text-brand-600 dark:text-brand-400 uppercase tracking-wider">
                  Day {day.day} • {day.date}
                </span>
                <h3 className="text-base font-bold text-ink-900 dark:text-white mt-0.5">{day.title}</h3>
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
    </div>
  );
}
