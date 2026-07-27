import { z } from "zod";

export const generateItinerarySchema = z
  .object({
    destination: z.string().min(2, "Enter a destination"),
    startDate: z.string().min(1, "Pick a start date"),
    endDate: z.string().min(1, "Pick an end date"),
    budget: z.coerce.number().positive("Enter a budget greater than 0"),
    currency: z.string().length(3),
    travelStyle: z.enum(["relaxed", "adventure", "luxury", "budget", "balanced"]),
    interests: z.array(z.string()),
  })
  .refine((data) => data.endDate >= data.startDate, {
    message: "End date must be on or after the start date",
    path: ["endDate"],
  });

export type GenerateItineraryFormValues = z.infer<typeof generateItinerarySchema>;
