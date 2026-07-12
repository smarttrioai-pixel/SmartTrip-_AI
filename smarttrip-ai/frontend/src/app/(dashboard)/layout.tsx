import type { ReactNode } from "react";

import { DashboardSidebar } from "@/shared/components/layout/DashboardSidebar";
import { MobileTabBar } from "@/shared/components/layout/MobileTabBar";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-ink-50 dark:bg-ink-900">
      <DashboardSidebar />
      <main className="flex-1 overflow-y-auto pb-20 lg:pb-0">{children}</main>
      <MobileTabBar />
    </div>
  );
}
