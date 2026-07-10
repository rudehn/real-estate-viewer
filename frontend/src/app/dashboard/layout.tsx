export const dynamic = "force-dynamic";

import { DashboardNav } from "@/components/layout/DashboardNav";
import { FilterSidebar } from "@/components/filters/FilterSidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-screen">
      <DashboardNav />
      <div className="flex flex-1 overflow-hidden">
        <FilterSidebar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
