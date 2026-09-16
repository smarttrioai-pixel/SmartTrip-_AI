import React, { useState } from 'react';
import { Calendar, MapPin, FileText, Plus, Sparkles, DollarSign, Image as ImageIcon } from 'lucide-react';
import type { DiaryEntry as DiaryEntryType, WritingStyle } from '../domain/types';
import { useAddNote, useAddExpense, useAddPlace, useAddPhoto, useGenerateDayStory } from '../hooks/useDiary';
import { DiaryPhotoGrid } from './DiaryPhotoGrid';
import { WritingStylePicker } from './WritingStylePicker';
import { Button } from '@/shared/components/ui/button';

interface DiaryEntryProps {
  entry: DiaryEntryType;
  tripId: string;
  isToday?: boolean;
}

export function DiaryEntry({ entry, tripId, isToday }: DiaryEntryProps) {
  const [newPlace, setNewPlace] = useState('');
  const [newNote, setNewNote] = useState('');
  
  const [expenseName, setExpenseName] = useState('');
  const [expenseAmount, setExpenseAmount] = useState('');
  const [expenseCurrency, setExpenseCurrency] = useState('USD');
  const [isAddingExpense, setIsAddingExpense] = useState(false);

  const [selectedStyle, setSelectedStyle] = useState<WritingStyle>(entry.writing_style as WritingStyle || 'journal');

  const addPlaceMutation = useAddPlace(tripId);
  const addNoteMutation = useAddNote(tripId);
  const addExpenseMutation = useAddExpense(tripId);
  const addPhotoMutation = useAddPhoto(tripId);
  const generateStoryMutation = useGenerateDayStory(tripId);

  const handleAddPlace = () => {
    if (!newPlace.trim()) return;
    addPlaceMutation.mutate({ entryId: entry.id, place: newPlace.trim() }, {
      onSuccess: () => setNewPlace('')
    });
  };

  const handleAddNote = () => {
    if (!newNote.trim()) return;
    addNoteMutation.mutate({ entryId: entry.id, note: newNote.trim() }, {
      onSuccess: () => setNewNote('')
    });
  };

  const handleAddExpense = () => {
    if (!expenseName.trim() || !expenseAmount) return;
    addExpenseMutation.mutate({ 
      entryId: entry.id, 
      name: expenseName.trim(), 
      amount: parseFloat(expenseAmount), 
      currency: expenseCurrency 
    }, {
      onSuccess: () => {
        setExpenseName('');
        setExpenseAmount('');
        setIsAddingExpense(false);
      }
    });
  };

  const handleGenerateStory = () => {
    generateStoryMutation.mutate({ entryId: entry.id, style: selectedStyle });
  };

  const isGenerating = generateStoryMutation.isPending;

  return (
    <div className={`bg-white dark:bg-ink-900 rounded-2xl border ${isToday ? 'border-brand-500 shadow-md' : 'border-ink-100 dark:border-ink-700 shadow-sm'} overflow-hidden`}>
      {/* Header */}
      <div className="bg-ink-50 dark:bg-ink-800/50 p-4 border-b border-ink-100 dark:border-ink-700 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 p-2 rounded-lg">
            <Calendar className="h-5 w-5" />
          </div>
          <div>
            <h3 className="font-bold text-ink-900 dark:text-white">
              {new Date(entry.date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </h3>
            {isToday && <span className="text-xs font-semibold text-brand-600 dark:text-brand-400">Today</span>}
          </div>
        </div>
      </div>

      <div className="p-5 flex flex-col gap-6">
        {/* Places Visited */}
        <div>
          <h4 className="text-sm font-semibold text-ink-700 dark:text-ink-300 flex items-center gap-2 mb-3">
            <MapPin className="h-4 w-4" /> Places Visited
          </h4>
          <div className="flex flex-wrap gap-2 mb-3">
            {entry.places_visited?.map((place, idx) => (
              <span key={idx} className="bg-ink-100 dark:bg-ink-800 text-ink-800 dark:text-ink-200 text-xs px-3 py-1.5 rounded-full">
                {place}
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input 
              value={newPlace} 
              onChange={(e) => setNewPlace(e.target.value)} 
              placeholder="Add a place..." 
              className="flex-1 text-sm h-9 px-3 rounded-md border border-input bg-background"
              onKeyDown={(e) => e.key === 'Enter' && handleAddPlace()}
            />
            <Button size="sm" onClick={handleAddPlace} disabled={!newPlace.trim() || addPlaceMutation.isPending}>Add</Button>
          </div>
        </div>

        {/* Notes */}
        <div>
          <h4 className="text-sm font-semibold text-ink-700 dark:text-ink-300 flex items-center gap-2 mb-3">
            <FileText className="h-4 w-4" /> Notes & Memories
          </h4>
          <div className="flex flex-col gap-2 mb-3">
            {entry.notes?.map((note, idx) => (
              <div key={idx} className="bg-ink-50 dark:bg-ink-800/50 p-3 rounded-lg text-sm text-ink-800 dark:text-ink-200">
                {note}
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <input 
              value={newNote} 
              onChange={(e) => setNewNote(e.target.value)} 
              placeholder="Jot down a quick memory..." 
              className="flex-1 text-sm h-9 px-3 rounded-md border border-input bg-background"
              onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
            />
            <Button size="sm" onClick={handleAddNote} disabled={!newNote.trim() || addNoteMutation.isPending}>Add</Button>
          </div>
        </div>

        {/* Photos */}
        <div>
          <h4 className="text-sm font-semibold text-ink-700 dark:text-ink-300 flex items-center gap-2 mb-3">
            <ImageIcon className="h-4 w-4" /> Photos
          </h4>
          <DiaryPhotoGrid 
            photos={entry.photos || []} 
            onAdd={(file) => addPhotoMutation.mutate({ entryId: entry.id, file })}
            isLoading={addPhotoMutation.isPending}
          />
        </div>

        {/* Expenses */}
        <div>
          <div className="flex justify-between items-center mb-3">
            <h4 className="text-sm font-semibold text-ink-700 dark:text-ink-300 flex items-center gap-2">
              <DollarSign className="h-4 w-4" /> Expenses
            </h4>
            {!isAddingExpense && (
              <Button variant="ghost" size="sm" onClick={() => setIsAddingExpense(true)} className="h-7 text-xs">
                <Plus className="h-3 w-3 mr-1" /> Add Expense
              </Button>
            )}
          </div>
          
          {entry.expenses?.length > 0 && (
            <div className="border border-ink-200 dark:border-ink-700 rounded-lg overflow-hidden mb-3">
              <table className="w-full text-sm">
                <thead className="bg-ink-50 dark:bg-ink-800 text-ink-500 text-left">
                  <tr>
                    <th className="px-4 py-2 font-medium">Item</th>
                    <th className="px-4 py-2 font-medium text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100 dark:divide-ink-800">
                  {entry.expenses.map((expense, idx) => (
                    <tr key={idx}>
                      <td className="px-4 py-2 text-ink-900 dark:text-ink-100">{expense.name}</td>
                      <td className="px-4 py-2 text-right font-medium text-ink-900 dark:text-ink-100">
                        {expense.amount.toFixed(2)} {expense.currency}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {isAddingExpense && (
            <div className="flex flex-wrap gap-2 p-3 bg-ink-50 dark:bg-ink-800/50 rounded-lg">
              <input 
                placeholder="What did you buy?" 
                value={expenseName}
                onChange={(e) => setExpenseName(e.target.value)}
                className="flex-1 min-w-[150px] h-9 px-3 rounded-md border border-input bg-background text-sm"
              />
              <input 
                type="number"
                placeholder="Amount" 
                value={expenseAmount}
                onChange={(e) => setExpenseAmount(e.target.value)}
                className="w-24 h-9 px-3 rounded-md border border-input bg-background text-sm"
              />
              <select 
                value={expenseCurrency}
                onChange={(e) => setExpenseCurrency(e.target.value)}
                className="h-9 px-3 rounded-md border border-ink-200 dark:border-ink-700 bg-white dark:bg-ink-900 text-sm"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="JPY">JPY</option>
              </select>
              <div className="flex gap-2 w-full justify-end mt-1">
                <Button variant="ghost" size="sm" onClick={() => setIsAddingExpense(false)}>Cancel</Button>
                <Button size="sm" onClick={handleAddExpense} disabled={!expenseName || !expenseAmount || addExpenseMutation.isPending}>Save</Button>
              </div>
            </div>
          )}
        </div>

        {/* AI Story */}
        <div className="mt-4 border-t border-ink-100 dark:border-ink-700 pt-6">
          <h4 className="text-sm font-semibold text-ink-700 dark:text-ink-300 flex items-center gap-2 mb-4">
            <Sparkles className="h-4 w-4 text-brand-500" /> Daily Story
          </h4>
          
          {entry.ai_story ? (
            <div className="bg-brand-50 dark:bg-brand-900/10 p-5 rounded-xl border border-brand-100 dark:border-brand-900/30">
              <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap text-ink-800 dark:text-ink-200 leading-relaxed">
                {entry.ai_story}
              </div>
              <div className="mt-4 flex justify-end">
                <Button variant="outline" size="sm" onClick={() => generateStoryMutation.mutate({ entryId: entry.id, style: selectedStyle })} disabled={isGenerating}>
                  <Sparkles className="h-4 w-4 mr-2" />
                  {isGenerating ? 'Regenerating...' : 'Regenerate Story'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="text-sm text-ink-500 dark:text-ink-400">
                Choose a writing style and let AI generate a story based on your places, notes, and photos.
              </p>
              <WritingStylePicker value={selectedStyle} onChange={setSelectedStyle} />
              <Button onClick={handleGenerateStory} disabled={isGenerating} className="self-start mt-2">
                <Sparkles className="h-4 w-4 mr-2" />
                {isGenerating ? 'Writing your story...' : 'Write My Story'}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
