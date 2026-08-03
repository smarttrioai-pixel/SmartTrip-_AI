import { useMutation } from "@tanstack/react-query";
import { diaryApi } from "@/features/diary/data/diaryApi";

export function useGenerateDiary() {
  return useMutation({
    mutationFn: (tripId: string) => diaryApi.generateDiary(tripId),
  });
}
