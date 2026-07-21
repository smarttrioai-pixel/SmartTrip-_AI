"use client";

import { LayoutDashboard, MapPinned, MessageCircle, User, Compass } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/shared/lib/utils";

const NAV_ITEMS = [
  { href: "/home", label: "Home", icon: LayoutDashboard },
  { href: "/trip-planner", label: "Plan", icon: Compass },
  { href: "/chat", label: "Chat", icon: MessageCircle },
  { href: "/saved-trips", label: "Trips", icon: MapPinned },
  { href: "/profile", label: "Profile", icon: User },
];

export function MobileTabBar() {
  const pathname = usePathname();

  return (
    <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-ink-100 bg-white/95 backdrop-blur dark:border-ink-700 dark:bg-ink-900/95 lg:hidden">
      {NAV_ITEMS.map((item) => {
        const isActive = pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-medium",
              isActive ? "text-brand-600" : "text-ink-400"
            )}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
