"use client";

import {
  LayoutDashboard,
  MapPinned,
  MessageCircle,
  User,
  LogOut,
  Compass,
  Brain,
  Navigation,
  Camera,
  BookOpen,
  BarChart3,
  Cpu,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCurrentUser, useLogout } from "@/features/authentication/hooks/useAuth";
import { cn } from "@/shared/lib/utils";

interface NavGroup {
  label: string;
  items: { href: string; label: string; icon: React.ElementType }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Plan",
    items: [
      { href: "/home", label: "Dashboard", icon: LayoutDashboard },
      { href: "/trip-planner", label: "AI Trip Planner", icon: Compass },
      { href: "/navigation", label: "Map & Navigation", icon: Navigation },
    ],
  },
  {
    label: "Explore",
    items: [
      { href: "/explore", label: "AR Explore", icon: Camera },
      { href: "/chat", label: "AI Chat", icon: MessageCircle },
    ],
  },
  {
    label: "My Trips",
    items: [
      { href: "/saved-trips", label: "Saved Trips", icon: MapPinned },
      { href: "/diary", label: "Travel Diary", icon: BookOpen },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/memory", label: "Cognitive Memory", icon: Brain },
      { href: "/profile", label: "Profile", icon: User },
    ],
  },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const { data: user } = useCurrentUser();
  const logout = useLogout();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-ink-100 bg-white px-3 py-6 dark:border-ink-700 dark:bg-ink-900 lg:flex">
      {/* Logo */}
      <Link
        href="/home"
        className="mb-6 flex items-center gap-2 px-2"
        aria-label="SmartTrip AI home"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white shrink-0">
          <Cpu className="h-4 w-4" />
        </div>
        <span className="font-display text-base font-semibold text-ink-900 dark:text-white">
          SmartTrip AI
        </span>
      </Link>

      {/* Navigation groups */}
      <nav className="flex flex-1 flex-col gap-5 overflow-y-auto" aria-label="Main navigation">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <p className="mb-1.5 px-2 text-[10px] font-semibold uppercase tracking-wider text-ink-400 dark:text-ink-600">
              {group.label}
            </p>
            <div className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const isActive = pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300"
                        : "text-ink-600 hover:bg-ink-50 dark:text-ink-300 dark:hover:bg-ink-800"
                    )}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <Icon
                      className={cn(
                        "h-4 w-4 shrink-0",
                        isActive
                          ? "text-brand-600 dark:text-brand-400"
                          : "text-ink-400 dark:text-ink-500"
                      )}
                      aria-hidden="true"
                    />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div className="mt-4 flex items-center gap-3 rounded-xl border border-ink-100 px-3 py-2.5 dark:border-ink-700">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700 dark:bg-brand-900/40 dark:text-brand-300 shrink-0"
          aria-hidden="true"
        >
          {user?.fullName?.slice(0, 2).toUpperCase() ?? "ST"}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink-900 dark:text-white">
            {user?.fullName ?? "Explorer"}
          </p>
          <p className="truncate text-xs text-ink-400 dark:text-ink-500">{user?.email}</p>
        </div>
        <button
          type="button"
          onClick={logout}
          aria-label="Log out"
          className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-50 hover:text-ink-700 dark:hover:bg-ink-800 dark:hover:text-ink-200"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </aside>
  );
}
