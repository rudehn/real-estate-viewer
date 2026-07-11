"use client";

import dynamic from "next/dynamic";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import { useFilters } from "@/lib/hooks/useFilters";
import { useTransactions } from "@/lib/hooks/useTransactions";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const PropertyMap = dynamic(() => import("@/components/map/PropertyMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-lg" />,
});
const NeighborhoodChoropleth = dynamic(
  () => import("@/components/map/NeighborhoodChoropleth"),
  { ssr: false, loading: () => <Skeleton className="h-full w-full rounded-lg" /> }
);

const MODES = ["sales", "neighborhoods"] as const;
type Mode = (typeof MODES)[number];

export default function MapPage() {
  const { filters } = useFilters();
  const [mode, setMode] = useQueryState<Mode>(
    "view",
    parseAsStringLiteral(MODES).withDefault("sales")
  );
  const { data, isLoading } = useTransactions(
    { ...filters, is_geocoded: true, limit: 10_000 },
    { enabled: mode === "sales" }
  );

  const transactions = data?.entities ?? [];
  const totalCount = data?.count ?? 0;

  return (
    <div className="flex flex-col h-full gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">Map Explorer</h1>
          <div className="flex rounded-md border overflow-hidden text-xs">
            {([
              ["sales", "Sales"],
              ["neighborhoods", "Neighborhoods"],
            ] as [Mode, string][]).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setMode(value)}
                className={cn(
                  "px-3 py-1.5 transition-colors",
                  mode === value
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:bg-muted"
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <span className="text-sm text-muted-foreground">
          {mode === "neighborhoods"
            ? "Market-sale statistics per appraisal neighborhood"
            : isLoading
              ? "Loading…"
              : totalCount > transactions.length
                ? `Showing the ${transactions.length.toLocaleString()} most recent of ${totalCount.toLocaleString()} geocoded sales`
                : `${transactions.length.toLocaleString()} geocoded sales`}
        </span>
      </div>
      <div className="flex-1 min-h-[500px]">
        {mode === "neighborhoods" ? (
          <NeighborhoodChoropleth
            sale_date__gte={filters.sale_date__gte}
            sale_date__lte={filters.sale_date__lte}
          />
        ) : isLoading ? (
          <Skeleton className="h-full w-full rounded-lg" />
        ) : (
          <PropertyMap transactions={transactions} />
        )}
      </div>
    </div>
  );
}
