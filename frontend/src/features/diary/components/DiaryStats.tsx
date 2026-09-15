import React from 'react';
import { MapPin, Image as ImageIcon, DollarSign, CalendarDays } from 'lucide-react';
import type { DiaryEntry } from '../domain/types';

interface DiaryStatsProps {
  entries: DiaryEntry[];
}

export function DiaryStats({ entries }: DiaryStatsProps) {
  const totalDays = entries.length;
  
  const totalPlaces = entries.reduce((acc, entry) => acc + (entry.places_visited?.length || 0), 0);
  const totalPhotos = entries.reduce((acc, entry) => acc + (entry.photos?.length || 0), 0);
  
  // For simplicity, summing up all expenses ignoring currency. In a real app, we'd group by currency.
  // We'll just show the primary currency of the first expense found, or USD.
  let primaryCurrency = 'USD';
  let totalExpenses = 0;
  
  entries.forEach(entry => {
    entry.expenses?.forEach(expense => {
      if (totalExpenses === 0) {
        primaryCurrency = expense.currency;
      }
      if (expense.currency === primaryCurrency) {
        totalExpenses += expense.amount;
      }
    });
  });

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div className="bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700 flex flex-col gap-1">
        <div className="flex items-center gap-2 text-ink-500 mb-1">
          <CalendarDays className="h-4 w-4" />
          <span className="text-xs font-semibold uppercase tracking-wider">Days Logged</span>
        </div>
        <p className="text-2xl font-bold text-ink-900 dark:text-white">{totalDays}</p>
      </div>

      <div className="bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700 flex flex-col gap-1">
        <div className="flex items-center gap-2 text-ink-500 mb-1">
          <MapPin className="h-4 w-4" />
          <span className="text-xs font-semibold uppercase tracking-wider">Places Explored</span>
        </div>
        <p className="text-2xl font-bold text-ink-900 dark:text-white">{totalPlaces}</p>
      </div>

      <div className="bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700 flex flex-col gap-1">
        <div className="flex items-center gap-2 text-ink-500 mb-1">
          <ImageIcon className="h-4 w-4" />
          <span className="text-xs font-semibold uppercase tracking-wider">Photos Taken</span>
        </div>
        <p className="text-2xl font-bold text-ink-900 dark:text-white">{totalPhotos}</p>
      </div>

      <div className="bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700 flex flex-col gap-1">
        <div className="flex items-center gap-2 text-ink-500 mb-1">
          <DollarSign className="h-4 w-4" />
          <span className="text-xs font-semibold uppercase tracking-wider">Total Spent</span>
        </div>
        <p className="text-2xl font-bold text-ink-900 dark:text-white">
          {totalExpenses > 0 ? `${totalExpenses.toFixed(0)} ${primaryCurrency}` : '0'}
        </p>
      </div>
    </div>
  );
}
