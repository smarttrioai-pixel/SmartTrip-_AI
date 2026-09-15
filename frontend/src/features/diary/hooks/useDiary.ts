import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { diaryApi } from '../data/diaryApi';
import type { WritingStyle } from '../domain/types';

export function useDiaryEntries(tripId: string) {
  return useQuery({
    queryKey: ['diary', tripId, 'entries'],
    queryFn: () => diaryApi.getEntries(tripId),
    enabled: !!tripId,
  });
}

export function useAddNote(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, note }: { entryId: string; note: string }) => diaryApi.addNote(tripId, entryId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diary', tripId] });
    },
  });
}

export function useAddExpense(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, name, amount, currency }: { entryId: string; name: string; amount: number; currency: string }) => 
      diaryApi.addExpense(tripId, entryId, name, amount, currency),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diary', tripId] });
    },
  });
}

export function useAddPlace(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, place }: { entryId: string; place: string }) => diaryApi.addPlace(tripId, entryId, place),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diary', tripId] });
    },
  });
}

export function useAddPhoto(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, file }: { entryId: string; file: File }) => diaryApi.addPhoto(tripId, entryId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diary', tripId] });
    },
  });
}

export function useGenerateDayStory(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ entryId, style }: { entryId: string; style: WritingStyle }) => diaryApi.generateStory(tripId, entryId, style),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diary', tripId] });
    },
  });
}

export function useGenerateTripStory(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => diaryApi.generateTripStory(tripId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diary', tripId] });
    },
  });
}

export function useTripStory(tripId: string) {
  return useQuery({
    queryKey: ['diary', tripId, 'story'],
    queryFn: () => diaryApi.getTripStory(tripId),
    enabled: !!tripId,
  });
}
