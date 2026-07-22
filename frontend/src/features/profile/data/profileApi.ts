import { apiClient } from "@/core/api/apiClient";
import type { Profile, UserPreferences } from "@/features/profile/domain/types";

interface PreferencesDto {
  budget: number | null;
  currency: string;
  language: string;
  travel_style: string;
  food_preference: string;
  accommodation: string;
  transport: string;
  accessibility_needs: string[];
  interests: string[];
}

interface ProfileDto {
  id: string;
  email: string;
  full_name: string;
  is_email_verified: boolean;
  preferences: PreferencesDto;
}

function toPreferences(dto: PreferencesDto): UserPreferences {
  return {
    budget: dto.budget,
    currency: dto.currency,
    language: dto.language,
    travelStyle: dto.travel_style as UserPreferences["travelStyle"],
    foodPreference: dto.food_preference,
    accommodation: dto.accommodation as UserPreferences["accommodation"],
    transport: dto.transport as UserPreferences["transport"],
    accessibilityNeeds: dto.accessibility_needs,
    interests: dto.interests,
  };
}

function toProfile(dto: ProfileDto): Profile {
  return {
    id: dto.id,
    email: dto.email,
    fullName: dto.full_name,
    isEmailVerified: dto.is_email_verified,
    preferences: toPreferences(dto.preferences),
  };
}

function toPreferencesDto(preferences: UserPreferences): PreferencesDto {
  return {
    budget: preferences.budget,
    currency: preferences.currency,
    language: preferences.language,
    travel_style: preferences.travelStyle,
    food_preference: preferences.foodPreference,
    accommodation: preferences.accommodation,
    transport: preferences.transport,
    accessibility_needs: preferences.accessibilityNeeds,
    interests: preferences.interests,
  };
}

export const profileApi = {
  async getProfile(): Promise<Profile> {
    const { data } = await apiClient.get<ProfileDto>("/profile");
    return toProfile(data);
  },

  async updateFullName(fullName: string): Promise<Profile> {
    const { data } = await apiClient.put<ProfileDto>("/profile", { full_name: fullName });
    return toProfile(data);
  },

  async updatePreferences(preferences: UserPreferences): Promise<Profile> {
    const { data } = await apiClient.put<ProfileDto>("/profile/preferences", toPreferencesDto(preferences));
    return toProfile(data);
  },
};
