"use client";

import { useFilters } from "@/lib/hooks/useFilters";
import { useTransactions } from "@/lib/hooks/useTransactions";
import { KpiCard } from "@/components/kpi/KpiCard";
import { MedianPriceTrend } from "@/components/charts/MedianPriceTrend";
import { TransactionVolume } from "@/components/charts/TransactionVolume";
import { SeasonalHeatmap } from "@/components/charts/SeasonalHeatmap";
import { computeMedian, formatCurrency } from "@/lib/utils/formatters";
import { Skeleton } from "@/components/ui/skeleton";

export default function OverviewPage() {
  const { filters } = useFilters();
  const { data, isLoading } = useTransactions({ ...filters, limit: 10_000 });

  const transactions = data?.entities ?? [];
  const totalCount = data?.count ?? 0;

  const prices = transactions.map((t) => t.sale_price).filter((p) => p > 0);
  const medianPrice = computeMedian(prices);
  const totalVolume = prices.reduce((s, p) => s + p, 0);
  const avgPricePerAcre =
    transactions.length > 0
      ? transactions.filter((t) => t.acres > 0).reduce(
          (s, t) => s + t.sale_price / t.acres,
          0
        ) / transactions.filter((t) => t.acres > 0).length
      : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-sm text-muted-foreground">Montgomery County, OH · Real estate transactions</p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Total Transactions"
          value={isLoading ? "…" : totalCount.toLocaleString()}
          icon="📋"
          isLoading={isLoading}
        />
        <KpiCard
          title="Median Sale Price"
          value={isLoading ? "…" : formatCurrency(medianPrice)}
          icon="💰"
          isLoading={isLoading}
        />
        <KpiCard
          title="Total Volume"
          value={isLoading ? "…" : formatCurrency(totalVolume)}
          icon="📦"
          isLoading={isLoading}
        />
        <KpiCard
          title="Avg $/Acre"
          value={isLoading ? "…" : formatCurrency(avgPricePerAcre)}
          icon="🌾"
          isLoading={isLoading}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          <>
            <Skeleton className="h-[280px] rounded-lg" />
            <Skeleton className="h-[280px] rounded-lg" />
          </>
        ) : (
          <>
            <MedianPriceTrend transactions={transactions} />
            <TransactionVolume transactions={transactions} />
          </>
        )}
      </div>

      {/* Seasonal Heatmap */}
      {!isLoading && transactions.length > 0 && (
        <SeasonalHeatmap transactions={transactions} />
      )}
    </div>
  );
}
