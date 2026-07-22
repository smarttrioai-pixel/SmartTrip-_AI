import type { Metadata } from "next";

import { SignupForm } from "@/features/authentication/components/SignupForm";
import { GoogleLoginButton } from "@/features/authentication/components/GoogleLoginButton";

export const metadata: Metadata = { title: "Create account — SmartTrip AI" };

export default function SignupPage() {
  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">Plan your next trip</h1>
        <p className="mt-1 text-sm text-ink-400">Create your account to get personalized itineraries.</p>
      </div>

      <SignupForm />

      <div className="flex items-center gap-3">
        <div className="h-px flex-1 bg-ink-100 dark:bg-ink-700" />
        <span className="text-xs font-medium uppercase tracking-wide text-ink-400">or</span>
        <div className="h-px flex-1 bg-ink-100 dark:bg-ink-700" />
      </div>

      <GoogleLoginButton />
    </div>
  );
}
