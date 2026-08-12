import { apiClient } from "@/core/api/apiClient";

export interface JournalDay {
  day: number;
  date: string;
  story: string;
  highlights: string[];
}

export interface DiaryResult {
  trip_id: string;
  destination: string;
  title: string;
  daily_journal: JournalDay[];
  expense_summary: {
    total_estimated_cost: number;
    currency: string;
    status: string;
    note: string;
  };
  ai_narrative_summary: string;
}

export const diaryApi = {
  async generateDiary(tripId: string): Promise<DiaryResult> {
    // Backend now looks up the real trip by id (verifying it belongs to
    // the authenticated user) rather than accepting a client-supplied
    // destination/highlights that could describe any trip at all.
    const { data } = await apiClient.post<DiaryResult>("/diary/generate", { trip_id: tripId });
    return data;
  },

  getExportPdfUrl(tripId: string): string {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
    return `${baseUrl}/diary/export-pdf/${tripId}`;
  },
};
