export type TravelStyle = "relaxed" | "adventure" | "luxury" | "budget" | "balanced";
export type Accommodation = "hotel" | "hostel" | "resort" | "homestay";
export type Transport = "flight" | "train" | "car" | "any";

export interface UserPreferences {
  budget: number | null;
  currency: string;
  language: string;
  travelStyle: TravelStyle;
  foodPreference: string;
  accommodation: Accommodation;
  transport: Transport;
  accessibilityNeeds: string[];
  interests: string[];
}

export interface Profile {
  id: string;
  email: string;
  fullName: string;
  isEmailVerified: boolean;
  preferences: UserPreferences;
}

export const TRAVEL_STYLES: { value: TravelStyle; label: string }[] = [
  { value: "balanced", label: "Balanced" },
  { value: "relaxed", label: "Relaxed" },
  { value: "adventure", label: "Adventure" },
  { value: "luxury", label: "Luxury" },
  { value: "budget", label: "Budget" },
];

export const ACCOMMODATIONS: { value: Accommodation; label: string }[] = [
  { value: "hotel", label: "Hotel" },
  { value: "hostel", label: "Hostel" },
  { value: "resort", label: "Resort" },
  { value: "homestay", label: "Homestay" },
];

export const TRANSPORT_MODES: { value: Transport; label: string }[] = [
  { value: "any", label: "No preference" },
  { value: "flight", label: "Flight" },
  { value: "train", label: "Train" },
  { value: "car", label: "Car" },
];

export const CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY", "AUD", "CAD"];

export const COMMON_INTERESTS = [
  "History",
  "Food",
  "Nature",
  "Nightlife",
  "Art & Museums",
  "Shopping",
  "Adventure Sports",
  "Beaches",
  "Photography",
  "Wildlife",
];
