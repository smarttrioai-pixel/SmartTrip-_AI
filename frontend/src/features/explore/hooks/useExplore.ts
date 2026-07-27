import { useMutation } from "@tanstack/react-query";
import { exploreApi } from "@/features/explore/data/exploreApi";

export function useAnalyzeLandmark() {
  return useMutation({
    mutationFn: ({ promptHint, imageB64 }: { promptHint: string; imageB64?: string }) =>
      exploreApi.analyzeLandmark(promptHint, imageB64),
  });
}

export function useAskLandmarkQA() {
  return useMutation({
    mutationFn: ({ landmarkName, question }: { landmarkName: string; question: string }) =>
      exploreApi.askQuestion(landmarkName, question),
  });
}
