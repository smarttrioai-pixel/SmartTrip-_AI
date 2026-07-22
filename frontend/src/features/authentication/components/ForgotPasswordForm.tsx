"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useForm } from "react-hook-form";

import { useForgotPassword } from "@/features/authentication/hooks/useAuth";
import {
  forgotPasswordSchema,
  type ForgotPasswordFormValues,
} from "@/features/authentication/domain/schemas";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

export function ForgotPasswordForm() {
  const forgotPassword = useForgotPassword();
  const {
    register,
    handleSubmit,
    getValues,
    formState: { errors },
  } = useForm<ForgotPasswordFormValues>({ resolver: zodResolver(forgotPasswordSchema) });

  const onSubmit = (values: ForgotPasswordFormValues) => forgotPassword.mutate(values.email);

  if (forgotPassword.isSuccess) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-2xl bg-brand-50 px-6 py-8 text-center dark:bg-brand-900/20">
        <CheckCircle2 className="h-10 w-10 text-brand-500" aria-hidden="true" />
        <div>
          <p className="font-medium text-ink-900 dark:text-white">Check your email</p>
          <p className="mt-1 text-sm text-ink-400">
            If an account exists for {getValues("email")}, we&rsquo;ve sent a reset link.
          </p>
        </div>
        <Link href="/login" className="text-sm font-medium text-brand-600 hover:underline">
          Back to log in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>
      <Input
        label="Email"
        type="email"
        autoComplete="email"
        placeholder="you@example.com"
        error={errors.email?.message}
        {...register("email")}
      />

      {forgotPassword.isError && (
        <p role="alert" className="rounded-lg bg-sunset-50 px-4 py-2.5 text-sm font-medium text-sunset-600">
          {forgotPassword.error.message}
        </p>
      )}

      <Button type="submit" size="lg" isLoading={forgotPassword.isPending} className="w-full">
        Send reset link
      </Button>

      <p className="text-center text-sm text-ink-400">
        Remembered it?{" "}
        <Link href="/login" className="font-medium text-brand-600 hover:underline">
          Log in
        </Link>
      </p>
    </form>
  );
}
