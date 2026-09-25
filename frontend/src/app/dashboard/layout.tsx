export const dynamic = "force-dynamic";

import { DashboardNav, MobileTabBar } from "@/components/layout/DashboardNav";
import { FilterSidebar } from "@/components/filters/FilterSidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-dvh">
      <DashboardNav />
      <div className="flex flex-1 min-h-0">
        <FilterSidebar />
        {/* On phones the bottom tab bar overlays the page, so leave room for it. */}
        <main className="flex-1 min-w-0 overflow-y-auto p-4 pb-[calc(5rem+env(safe-area-inset-bottom))] lg:p-6">
          {children}
        </main>
      </div>
      <MobileTabBar />
    </div>
  );
}
