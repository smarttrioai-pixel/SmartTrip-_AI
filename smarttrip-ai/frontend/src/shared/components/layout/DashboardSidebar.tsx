"use client";

import { LayoutDashboard, MapPinned, MessageCircle, User, LogOut, Compass } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCurrentUser, useLogout } from "@/features/authentication/hooks/useAuth";
import { cn } from "@/shared/lib/utils";

const NAV_ITEMS = [
  { href: "/home", label: "Dashboard", icon: LayoutDashboard },
  { href: "/trip-planner", label: "AI Trip Planner", icon: Compass },
  { href: "/chat", label: "AI Chat", icon: MessageCircle },
  { href: "/saved-trips", label: "Saved Trips", icon: MapPinned },
  { href: "/profile", label: "Profile", icon: User },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-ink-100 bg-white px-4 py-6 dark:border-ink-700 dark:bg-ink-900 lg:flex">
      <Link href="/home" className="mb-8 px-2 font-display text-lg font-semibold text-ink-900 dark:text-white">
        SmartTrip AI
      </Link>

      <nav className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                  : "text-ink-700 hover:bg-ink-50 dark:text-ink-100 dark:hover:bg-ink-800"
              )}
            >
              <Icon className="h-4.5 w-4.5" aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex items-center gap-3 rounded-xl border border-ink-100 px-3 py-2.5 dark:border-ink-700">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700 dark:bg-brand-900/40 dark:text-brand-300">
          {user?.fullName?.slice(0, 2).toUpperCase() ?? "…"}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink-900 dark:text-white">{user?.fullName ?? "Loading…"}</p>
          <p className="truncate text-xs text-ink-400">{user?.email}</p>
        </div>
        <button
          type="button"
          onClick={logout}
          aria-label="Log out"
          className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-50 hover:text-ink-700 dark:hover:bg-ink-800"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </aside>
  );
}
