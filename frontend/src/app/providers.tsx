"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";

import { AuthStateListener } from "@/features/authentication/components/AuthStateListener";

export function Providers({ children }: { children: ReactNode }) {
  // One QueryClient per browser session (not per render) — created in state
  // so it survives re-renders but isn't shared across users on the server.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <AuthStateListener />
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}
