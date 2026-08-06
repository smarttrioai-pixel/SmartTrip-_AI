"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2 } from "lucide-react";
import { useForm, Controller } from "react-hook-form";

import { useUpdatePreferences } from "@/features/profile/hooks/useProfile";
import { preferencesSchema, type PreferencesFormValues } from "@/features/profile/domain/schemas";
import {
  ACCOMMODATIONS,
  COMMON_INTERESTS,
  CURRENCIES,
  TRANSPORT_MODES,
  TRAVEL_STYLES,
  type Profile,
} from "@/features/profile/domain/types";
import { Button } from "@/shared/components/ui/button";
import { ChipGroup } from "@/shared/components/ui/chip-group";
import { Input } from "@/shared/components/ui/input";
import { Select } from "@/shared/components/ui/select";

export function PreferencesForm({ profile }: { profile: Profile }) {
  const updatePreferences = useUpdatePreferences();
  const {
    register,
    handleSubmit,
    control,
    formState: { isDirty },
  } = useForm<PreferencesFormValues>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: {
  ...profile.preferences,
  interests: profile.preferences?.interests ?? [],
  accessibilityNeeds:
    profile.preferences?.accessibilityNeeds ?? [],
},
  });

  const onSubmit = (values: PreferencesFormValues) => updatePreferences.mutate(values);

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-5 rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800"
    >
      <div>
        <h2 className="font-display text-lg font-semibold text-ink-900 dark:text-white">Travel preferences</h2>
        <p className="mt-1 text-sm text-ink-400">
          Used by the AI Trip Planner to personalize itineraries and by the recommendation engine to
          weight suggestions (Module 3: Preference Learning builds on top of this over time).
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Input label="Default budget" type="number" min={0} step="1" {...register("budget")} />
        <Controller
          control={control}
          name="currency"
          render={({ field }) => (
            <Select label="Currency" options={CURRENCIES.map((c) => ({ value: c, label: c }))} {...field} />
          )}
        />
        <Controller
          control={control}
          name="travelStyle"
          render={({ field }) => <Select label="Travel style" options={TRAVEL_STYLES} {...field} />}
        />
        <Input label="Food preference" placeholder="e.g. vegetarian, halal, no restrictions" {...register("foodPreference")} />
        <Controller
          control={control}
          name="accommodation"
          render={({ field }) => <Select label="Accommodation" options={ACCOMMODATIONS} {...field} />}
        />
        <Controller
          control={control}
          name="transport"
          render={({ field }) => <Select label="Preferred transport" options={TRANSPORT_MODES} {...field} />}
        />
        <Input label="Language" placeholder="en" {...register("language")} />
      </div>

      <Controller
        control={control}
        name="interests"
        render={({ field }) => (
          <ChipGroup label="Interests" options={COMMON_INTERESTS} value={field.value} onChange={field.onChange} />
        )}
      />

      <div className="flex items-center gap-3">
        <Button type="submit" isLoading={updatePreferences.isPending} disabled={!isDirty}>
          Save preferences
        </Button>
        {updatePreferences.isSuccess && (
          <span className="flex items-center gap-1.5 text-sm text-brand-600">
            <CheckCircle2 className="h-4 w-4" /> Saved
          </span>
        )}
        {updatePreferences.isError && (
          <span className="text-sm text-sunset-600">{updatePreferences.error.message}</span>
        )}
      </div>
    </form>
  );
}
