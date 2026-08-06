import { apiClient } from "@/core/api/apiClient";

export interface LandmarkAnalysisResult {
  landmark_name: string;
  confidence: number;
  category: string;
  historical_background: string;
  architectural_highlights: string[];
  cultural_importance: string;
  photography_spots: string[];
  nearby_attractions: string[];
  thumbnail_url?: string;
  wikipedia_url?: string;
}

export interface LandmarkQAResponse {
  landmark_name: string;
  question: string;
  answer: string;
}

export const exploreApi = {
  async analyzeLandmark(promptHint: string = "", imageB64?: string): Promise<LandmarkAnalysisResult> {
    const { data } = await apiClient.post<LandmarkAnalysisResult>("/explore/analyze-landmark", {
      prompt_hint: promptHint,
      image_b64: imageB64 ?? null,
    });
    return data;
  },

  async askQuestion(landmarkName: string, question: string): Promise<LandmarkQAResponse> {
    const { data } = await apiClient.post<LandmarkQAResponse>("/explore/qa", {
      landmark_name: landmarkName,
      question,
    });
    return data;
  },
};
