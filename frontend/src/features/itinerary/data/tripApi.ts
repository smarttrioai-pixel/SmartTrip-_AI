import { apiClient } from "@/core/api/apiClient";
import type { GenerateItineraryPayload, Trip } from "@/features/itinerary/domain/types";

interface ActivityDto {
  time: string;
  title: string;
  description: string;
  location: string;
  estimated_cost: number;
}

interface DayPlanDto {
  day_number: number;
  title: string;
  activities: ActivityDto[];
}

interface TripDto {
  id: string;
  destination: string;
  start_date: string;
  end_date: string;
  budget: number;
  currency: string;
  travel_style: string;
  days: DayPlanDto[];
  estimated_total_cost: number;
  is_saved: boolean;
}

function toTrip(dto: TripDto): Trip {
  return {
    id: dto.id,
    destination: dto.destination,
    startDate: dto.start_date,
    endDate: dto.end_date,
    budget: dto.budget,
    currency: dto.currency,
    travelStyle: dto.travel_style,
    estimatedTotalCost: dto.estimated_total_cost,
    isSaved: dto.is_saved,
    days: dto.days.map((day) => ({
      dayNumber: day.day_number,
      title: day.title,
      activities: day.activities.map((a) => ({
        time: a.time,
        title: a.title,
        description: a.description,
        location: a.location,
        estimatedCost: a.estimated_cost,
      })),
    })),
  };
}

export const tripApi = {
  async generate(payload: GenerateItineraryPayload): Promise<Trip> {
    const { data } = await apiClient.post<TripDto>("/trips/generate", {
      destination: payload.destination,
      start_date: payload.startDate,
      end_date: payload.endDate,
      budget: payload.budget,
      currency: payload.currency,
      travel_style: payload.travelStyle,
      interests: payload.interests,
    });
    return toTrip(data);
  },

  async list(savedOnly = false): Promise<Trip[]> {
    const { data } = await apiClient.get<TripDto[]>("/trips", { params: { saved_only: savedOnly } });
    return data.map(toTrip);
  },

  async setSaved(tripId: string, isSaved: boolean): Promise<void> {
    await apiClient.patch(`/trips/${tripId}/save`, { is_saved: isSaved });
  },

  async remove(tripId: string): Promise<void> {
    await apiClient.delete(`/trips/${tripId}`);
  },
};
