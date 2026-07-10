"use client";

import { useState } from "react";
import { useFilters } from "@/lib/hooks/useFilters";
import { useDataHealth, useMarketStats } from "@/lib/hooks/useAnalytics";
import { KpiCard } from "@/components/kpi/KpiCard";
import { MedianPriceTrend } from "@/components/charts/MedianPriceTrend";
import { TransactionVolume } from "@/components/charts/TransactionVolume";
import { SeasonalHeatmap } from "@/components/charts/SeasonalHeatmap";
import { formatCurrency, formatDate } from "@/lib/utils/formatters";
import type { Granularity } from "@/lib/types/api";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function pctChange(cur: number, prev: number): number | undefined {
  if (!prev || !cur) return undefined;
  return ((cur - prev) / prev) * 100;
}

export default function OverviewPage() {
  const { filters } = useFilters();
  const [priceGran, setPriceGran] = useState<Granularity>("year");
  const [volumeGran, setVolumeGran] = useState<Granularity>("year");

  // All aggregation happens server-side over the full filtered set —
  // no row cap, so the KPIs are exact.
  const { data: totals, isLoading } = useMarketStats({ ...filters, granularity: "all" });
  const { data: priceBuckets = [], isLoading: priceLoading } = useMarketStats({
    ...filters,
    granularity: priceGran,
  });
  const { data: volumeBuckets = [], isLoading: volumeLoading } = useMarketStats({
    ...filters,
    granularity: volumeGran,
  });
  const { data: monthly = [] } = useMarketStats({ ...filters, granularity: "month" });

  // Momentum: trailing 12 months vs the 12 months before, with the user's
  // non-date filters applied (the date filter is overridden on purpose).
  const windowFilters = { ...filters, granularity: "all" as const };
  const { data: last12 } = useMarketStats({
    ...windowFilters,
    sale_date__gte: isoDaysAgo(365),
    sale_date__lte: isoDaysAgo(0),
  });
  const { data: prior12 } = useMarketStats({
    ...windowFilters,
    sale_date__gte: isoDaysAgo(730),
    sale_date__lte: isoDaysAgo(366),
  });

  const all = totals?.[0];
  const cur = last12?.[0];
  const prev = prior12?.[0];
  const { data: health } = useDataHealth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-sm text-muted-foreground">
          Montgomery County, OH · Arm&apos;s-length market sales
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Market Sales"
          value={(all?.transaction_count ?? 0).toLocaleString()}
          delta={pctChange(cur?.transaction_count ?? 0, prev?.transaction_count ?? 0)}
          isLoading={isLoading}
        />
        <KpiCard
          title="Median Sale Price"
          value={formatCurrency(all?.median_price ?? 0)}
          delta={pctChange(cur?.median_price ?? 0, prev?.median_price ?? 0)}
          isLoading={isLoading}
        />
        <KpiCard
          title="Average Sale Price"
          value={formatCurrency(all?.avg_price ?? 0)}
          delta={pctChange(cur?.avg_price ?? 0, prev?.avg_price ?? 0)}
          isLoading={isLoading}
        />
        <KpiCard
          title="Total Volume"
          value={formatCurrency(all?.total_volume ?? 0)}
          delta={pctChange(cur?.total_volume ?? 0, prev?.total_volume ?? 0)}
          isLoading={isLoading}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MedianPriceTrend
          data={priceBuckets}
          granularity={priceGran}
          onGranularityChange={setPriceGran}
          isLoading={priceLoading}
        />
        <TransactionVolume
          data={volumeBuckets}
          granularity={volumeGran}
          onGranularityChange={setVolumeGran}
          isLoading={volumeLoading}
        />
      </div>

      {/* Seasonal Heatmap */}
      <SeasonalHeatmap monthly={monthly} />

      {/* Data health strip */}
      {health && (
        <p className="text-xs text-muted-foreground">
          {health.total_transactions.toLocaleString()} recorded transfers on{" "}
          {health.total_parcels.toLocaleString()} parcels
          {" · "}latest sale {health.latest_sale_date ? formatDate(health.latest_sale_date) : "—"}
          {" · "}last ingest {health.last_ingest_at ? formatDate(health.last_ingest_at.slice(0, 10)) : "—"}
          {" · "}{health.geocoded_pct.toFixed(0)}% of parcels geocoded
          {" · "}{health.market_sale_pct.toFixed(0)}% of transfers are arm&apos;s-length market sales
        </p>
      )}
    </div>
  );
}
