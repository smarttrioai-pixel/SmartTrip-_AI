"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2 } from "lucide-react";
import { useForm } from "react-hook-form";

import { useUpdateFullName } from "@/features/profile/hooks/useProfile";
import { profileDetailsSchema, type ProfileDetailsFormValues } from "@/features/profile/domain/schemas";
import type { Profile } from "@/features/profile/domain/types";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

export function ProfileDetailsForm({ profile }: { profile: Profile }) {
  const updateFullName = useUpdateFullName();
  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<ProfileDetailsFormValues>({
    resolver: zodResolver(profileDetailsSchema),
    defaultValues: { fullName: profile.fullName },
  });

  const onSubmit = (values: ProfileDetailsFormValues) => updateFullName.mutate(values.fullName);

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 rounded-2xl border border-ink-100 bg-white p-6 dark:border-ink-700 dark:bg-ink-800">
      <h2 className="font-display text-lg font-semibold text-ink-900 dark:text-white">Your details</h2>

      <Input label="Full name" error={errors.fullName?.message} {...register("fullName")} />
      <Input label="Email" value={profile.email} disabled className="opacity-60" />

      <div className="flex items-center gap-3">
        <Button type="submit" isLoading={updateFullName.isPending} disabled={!isDirty}>
          Save changes
        </Button>
        {updateFullName.isSuccess && (
          <span className="flex items-center gap-1.5 text-sm text-brand-600">
            <CheckCircle2 className="h-4 w-4" /> Saved
          </span>
        )}
        {updateFullName.isError && (
          <span className="text-sm text-sunset-600">{updateFullName.error.message}</span>
        )}
      </div>
    </form>
  );
}
