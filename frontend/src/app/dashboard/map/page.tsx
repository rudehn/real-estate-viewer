"use client";

import dynamic from "next/dynamic";
import { useFilters } from "@/lib/hooks/useFilters";
import { useTransactions } from "@/lib/hooks/useTransactions";
import { Skeleton } from "@/components/ui/skeleton";

const PropertyMap = dynamic(() => import("@/components/map/PropertyMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-lg" />,
});

export default function MapPage() {
  const { filters } = useFilters();
  const { data, isLoading } = useTransactions({ ...filters, is_geocoded: true, limit: 10_000 });

  const transactions = data?.entities ?? [];
  const totalCount = data?.count ?? 0;

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Map Explorer</h1>
        <span className="text-sm text-muted-foreground">
          {isLoading
            ? "Loading…"
            : totalCount > transactions.length
              ? `Showing the ${transactions.length.toLocaleString()} most recent of ${totalCount.toLocaleString()} geocoded sales`
              : `${transactions.length.toLocaleString()} geocoded sales`}
        </span>
      </div>
      <div className="flex-1 min-h-[500px]">
        {isLoading ? (
          <Skeleton className="h-full w-full rounded-lg" />
        ) : (
          <PropertyMap transactions={transactions} />
        )}
      </div>
    </div>
  );
}
