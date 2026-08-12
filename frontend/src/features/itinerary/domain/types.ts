export interface Explanation {
  reasonText: string;
  budgetMatch: number;
  interestMatch: number;
  contextScore: number;
  confidence: number;
}

export interface Activity {
  time: string;
  title: string;
  description: string;
  location: string;
  estimatedCost: number;
  category?: string | null;
  reason?: string | null;
  mealType?: string | null;
  foodQuery?: string | null;
  explanation: Explanation | null;
}

export interface DayPlan {
  dayNumber: number;
  title: string;
  activities: Activity[];
}

export interface Trip {
  id: string;
  destination: string;
  startDate: string;
  endDate: string;
  budget: number;
  currency: string;
  travelStyle: string;
  days: DayPlan[];
  estimatedTotalCost: number;
  isSaved: boolean;
}

export interface GenerateItineraryPayload {
  destination: string;
  startDate: string;
  endDate: string;
  budget: number;
  currency: string;
  travelStyle: string;
  interests: string[];
  transport: string;
}
