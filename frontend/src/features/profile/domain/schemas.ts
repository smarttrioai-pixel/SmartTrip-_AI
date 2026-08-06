import { z } from "zod";

export const profileDetailsSchema = z.object({
  fullName: z.string().min(2, "Enter your full name").max(255),
});
export type ProfileDetailsFormValues = z.infer<typeof profileDetailsSchema>;

export const preferencesSchema = z.object({
  budget: z.coerce.number().min(0).nullable(),
  currency: z.string().length(3),
  language: z.string().min(2).max(10),
  travelStyle: z.enum(["relaxed", "adventure", "luxury", "budget", "balanced"]),
  foodPreference: z.string().min(1),
  accommodation: z.enum(["hotel", "hostel", "resort", "homestay"]),
  transport: z.enum(["flight", "train", "car", "any"]),
  accessibilityNeeds: z.array(z.string()),
  interests: z.array(z.string()),
});
export type PreferencesFormValues = z.infer<typeof preferencesSchema>;
