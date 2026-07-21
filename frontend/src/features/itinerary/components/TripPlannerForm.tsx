"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";

import { useGenerateItinerary } from "@/features/itinerary/hooks/useTrips";
import { generateItinerarySchema, type GenerateItineraryFormValues } from "@/features/itinerary/domain/schemas";
import type { Trip } from "@/features/itinerary/domain/types";
import { TRAVEL_STYLES, CURRENCIES, COMMON_INTERESTS } from "@/features/profile/domain/types";
import { Button } from "@/shared/components/ui/button";
import { ChipGroup } from "@/shared/components/ui/chip-group";
import { Input } from "@/shared/components/ui/input";
import { Select } from "@/shared/components/ui/select";

export function TripPlannerForm({ onGenerated }: { onGenerated: (trip: Trip) => void }) {
  const generate = useGenerateItinerary();
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<GenerateItineraryFormValues>({
    resolver: zodResolver(generateItinerarySchema),
    defaultValues: { currency: "USD", travelStyle: "balanced", interests: [] },
  });

  const onSubmit = (values: GenerateItineraryFormValues) =>
    generate.mutate(values, { onSuccess: onGenerated });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>
      <Input label="Destination" placeholder="e.g. Kyoto, Japan" error={errors.destination?.message} {...register("destination")} />

      <div className="grid grid-cols-2 gap-4">
        <Input label="Start date" type="date" error={errors.startDate?.message} {...register("startDate")} />
        <Input label="End date" type="date" error={errors.endDate?.message} {...register("endDate")} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Input label="Budget" type="number" min={1} error={errors.budget?.message} {...register("budget")} />
        <Controller
          control={control}
          name="currency"
          render={({ field }) => <Select label="Currency" options={CURRENCIES.map((c) => ({ value: c, label: c }))} {...field} />}
        />
      </div>

      <Controller
        control={control}
        name="travelStyle"
        render={({ field }) => <Select label="Travel style" options={TRAVEL_STYLES} {...field} />}
      />

      <Controller
        control={control}
        name="interests"
        render={({ field }) => (
          <ChipGroup label="Interests" options={COMMON_INTERESTS} value={field.value} onChange={field.onChange} />
        )}
      />

      {generate.isError && (
        <p role="alert" className="rounded-lg bg-sunset-50 px-4 py-2.5 text-sm font-medium text-sunset-600">
          {generate.error.message}
        </p>
      )}

      <Button type="submit" size="lg" isLoading={generate.isPending} className="w-full">
        Generate itinerary
      </Button>
    </form>
  );
}
