import { apiClient } from "@/core/api/apiClient";
import type { User } from "@/features/authentication/domain/types";

/** Shape returned by the FastAPI backend's /profile endpoints — snake_case, as-is over the wire. */
interface ProfileDto {
  id: string;
  email: string;
  full_name: string;
  is_email_verified: boolean;
}

function toUser(dto: ProfileDto): User {
  return {
    id: dto.id,
    email: dto.email,
    fullName: dto.full_name,
    isEmailVerified: dto.is_email_verified,
  };
}

export const authApi = {
  /**
   * Called once right after Firebase signup/login succeeds. Ensures the
   * Firestore profile doc exists (the backend also lazily creates it on any
   * authenticated request, but this call applies the chosen display name
   * immediately rather than waiting on Firebase's own `name` claim to catch up).
   */
  async syncProfile(fullName?: string): Promise<User> {
    const { data } = await apiClient.post<ProfileDto>(
      "/profile/sync",
      fullName ? { full_name: fullName } : {}
    );
    return toUser(data);
  },

  async getCurrentProfile(): Promise<User> {
    const { data } = await apiClient.get<ProfileDto>("/profile");
    return toUser(data);
  },
};
