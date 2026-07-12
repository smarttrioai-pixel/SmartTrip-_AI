"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useForm } from "react-hook-form";

import { useLogin } from "@/features/authentication/hooks/useAuth";
import { loginSchema, type LoginFormValues } from "@/features/authentication/domain/schemas";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

export function LoginForm() {
  const login = useLogin();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = (values: LoginFormValues) => login.mutate(values);

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
      <Input
        label="Password"
        type="password"
        autoComplete="current-password"
        placeholder="••••••••"
        error={errors.password?.message}
        {...register("password")}
      />

      <div className="flex justify-end">
        <Link href="/forgot-password" className="text-sm font-medium text-brand-600 hover:underline">
          Forgot password?
        </Link>
      </div>

      {login.isError && (
        <p role="alert" className="rounded-lg bg-sunset-50 px-4 py-2.5 text-sm font-medium text-sunset-600">
          {login.error.message}
        </p>
      )}

      <Button type="submit" size="lg" isLoading={login.isPending} className="w-full">
        Log in
      </Button>

      <p className="text-center text-sm text-ink-400">
        New to SmartTrip?{" "}
        <Link href="/signup" className="font-medium text-brand-600 hover:underline">
          Create an account
        </Link>
      </p>
    </form>
  );
}
