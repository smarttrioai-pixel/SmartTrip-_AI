import { useMutation, useQueryClient } from "@tanstack/react-query";
import { tripApi } from "@/features/itinerary/data/tripApi";
import type {
  ModifyItineraryRequest,
  ReplaceActivityRequest,
  MoveActivityRequest,
  ReorderRequest,
} from "@/features/itinerary/domain/types";

export function useModifyItinerary(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ModifyItineraryRequest) => tripApi.modifyItinerary(tripId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trip", tripId] }),
  });
}

export function useAlternatives() {
  return useMutation({
    mutationFn: ({ tripId, activityId, dayNumber }: { tripId: string, activityId: string, dayNumber: number }) => 
      tripApi.getAlternatives(tripId, activityId, dayNumber)
  });
}

export function useReplaceActivity(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, payload }: { activityId: string, payload: ReplaceActivityRequest }) => 
      tripApi.replaceActivity(tripId, activityId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trip", tripId] }),
  });
}

export function useMoveActivity(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, payload }: { activityId: string, payload: MoveActivityRequest }) => 
      tripApi.moveActivity(tripId, activityId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trip", tripId] }),
  });
}

export function useRemoveActivity(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ activityId, dayNumber }: { activityId: string, dayNumber: number }) => 
      tripApi.removeActivity(tripId, activityId, dayNumber),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trip", tripId] }),
  });
}

export function useReorderActivities(tripId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReorderRequest) => tripApi.reorderActivities(tripId, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trip", tripId] }),
  });
}
