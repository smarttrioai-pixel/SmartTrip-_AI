export interface DiaryPhoto {
  url?: string;
  image_b64?: string;
  gemini_description?: string;
  added_at: string;
}

export interface DiaryExpense {
  name: string;
  amount: number;
  currency: string;
}

export interface DiaryEntry {
  id: string;
  trip_id: string;
  user_id: string;
  date: string; // YYYY-MM-DD
  places_visited: string[];
  notes: string[];
  photos: DiaryPhoto[];
  expenses: DiaryExpense[];
  ratings: Record<string, number>;
  ai_story?: string | null;
  writing_style: string;
  created_at: string;
  updated_at: string;
}

export type WritingStyle = 'simple' | 'journal' | 'blog' | 'emotional' | 'summary' | 'social';

export const WRITING_STYLES: { value: WritingStyle; label: string; description: string }[] = [
  { value: 'simple', label: 'Simple', description: 'Clean and straightforward' },
  { value: 'journal', label: 'Personal Journal', description: 'First-person reflection' },
  { value: 'blog', label: 'Travel Blog', description: 'Engaging narrative with tips' },
  { value: 'emotional', label: 'Emotional', description: 'Feelings and memories' },
  { value: 'summary', label: 'Short Summary', description: 'Bullet points and highlights' },
  { value: 'social', label: 'Social Caption', description: 'Perfect for Instagram' },
];

export interface TripStory {
  trip_id: string;
  content: string;
  generated_at: string;
}
