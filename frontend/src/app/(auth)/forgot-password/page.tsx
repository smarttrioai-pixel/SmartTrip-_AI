import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/features/authentication/components/ForgotPasswordForm";

export const metadata: Metadata = { title: "Reset password — SmartTrip AI" };

export default function ForgotPasswordPage() {
  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">Reset your password</h1>
        <p className="mt-1 text-sm text-ink-400">
          Enter the email on your account and we&rsquo;ll send you a link to reset it.
        </p>
      </div>
      <ForgotPasswordForm />
    </div>
  );
}
