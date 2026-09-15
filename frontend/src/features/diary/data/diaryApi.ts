import { apiClient } from '@/core/api/apiClient';
import type { DiaryEntry, TripStory, WritingStyle } from '../domain/types';

export const diaryApi = {
  getEntries: async (tripId: string): Promise<DiaryEntry[]> => {
    const { data } = await apiClient.get<DiaryEntry[]>(`/diary/${tripId}/entries`);
    return data;
  },

  createEntry: async (tripId: string, date: string): Promise<DiaryEntry> => {
    const { data } = await apiClient.post<DiaryEntry>(`/diary/${tripId}/entries`, { date });
    return data;
  },

  addNote: async (tripId: string, entryId: string, note: string): Promise<DiaryEntry> => {
    const { data } = await apiClient.post<DiaryEntry>(`/diary/${tripId}/entries/${entryId}/note`, { note });
    return data;
  },

  addExpense: async (tripId: string, entryId: string, name: string, amount: number, currency: string): Promise<DiaryEntry> => {
    const { data } = await apiClient.post<DiaryEntry>(`/diary/${tripId}/entries/${entryId}/expense`, { name, amount, currency });
    return data;
  },

  addPlace: async (tripId: string, entryId: string, place: string): Promise<DiaryEntry> => {
    const { data } = await apiClient.post<DiaryEntry>(`/diary/${tripId}/entries/${entryId}/place`, { place });
    return data;
  },

  addPhoto: async (tripId: string, entryId: string, file: File): Promise<DiaryEntry> => {
    const form = new FormData();
    form.append('file', file);
    const { data } = await apiClient.post<DiaryEntry>(
      `/diary/${tripId}/entries/${entryId}/photo`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return data;
  },

  generateStory: async (tripId: string, entryId: string, writing_style: WritingStyle = 'journal'): Promise<DiaryEntry> => {
    const { data } = await apiClient.post<DiaryEntry>(`/diary/${tripId}/entries/${entryId}/generate`, { writing_style });
    return data;
  },

  updateEntry: async (tripId: string, entryId: string, updates: Partial<DiaryEntry>): Promise<DiaryEntry> => {
    const { data } = await apiClient.put<DiaryEntry>(`/diary/${tripId}/entries/${entryId}`, updates);
    return data;
  },

  getTripStory: async (tripId: string): Promise<TripStory | null> => {
    try {
      const { data } = await apiClient.get<TripStory>(`/diary/${tripId}/story`);
      return data;
    } catch {
      return null;
    }
  },

  generateTripStory: async (tripId: string): Promise<TripStory> => {
    const { data } = await apiClient.post<TripStory>(`/diary/${tripId}/story/generate`);
    return data;
  },

  exportPdf: (tripId: string): void => {
    window.open(`/api/v1/diary/${tripId}/export-pdf`, '_blank');
  },
};
