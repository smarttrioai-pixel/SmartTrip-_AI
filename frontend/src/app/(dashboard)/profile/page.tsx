"use client";

import { useProfile } from "@/features/profile/hooks/useProfile";
import { ProfileDetailsForm } from "@/features/profile/components/ProfileDetailsForm";
import { PreferencesForm } from "@/features/profile/components/PreferencesForm";

export default function ProfilePage() {
  const { data: profile, isLoading, isError, error, refetch } = useProfile();

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">Profile</h1>
      <p className="mt-1 text-sm text-ink-400">Manage your details and travel preferences.</p>

      <div className="mt-8 flex flex-col gap-6">
        {isLoading && (
          <div className="flex flex-col gap-4">
            <div className="h-40 animate-pulse rounded-2xl bg-ink-100 dark:bg-ink-800" />
            <div className="h-72 animate-pulse rounded-2xl bg-ink-100 dark:bg-ink-800" />
          </div>
        )}

        {isError && (
          <div className="rounded-2xl border border-sunset-500/30 bg-sunset-50 p-6 text-center">
            <p className="text-sm font-medium text-sunset-600">{error.message}</p>
            <button onClick={() => refetch()} className="mt-2 text-sm font-medium text-brand-600 hover:underline">
              Try again
            </button>
          </div>
        )}

        {profile && (
          <>
            <ProfileDetailsForm profile={profile} />
            <PreferencesForm profile={profile} />
          </>
        )}
      </div>
    </div>
  );
}
