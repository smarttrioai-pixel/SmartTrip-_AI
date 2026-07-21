export interface Activity {
  time: string;
  title: string;
  description: string;
  location: string;
  estimatedCost: number;
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
}
