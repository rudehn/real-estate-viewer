"use client";

import { useFilters } from "@/lib/hooks/useFilters";
import { useTransactions } from "@/lib/hooks/useTransactions";
import { useTopBuyers, useTopSellers, useNeighborhoods, useNeighborhoodTrends, useDistressedSales, useStaleParcels } from "@/lib/hooks/useAnalytics";
import { NeighborhoodRankings } from "@/components/charts/NeighborhoodRankings";
import { NeighborhoodTrends } from "@/components/charts/NeighborhoodTrends";
import { TopBuyersSellers } from "@/components/charts/TopBuyersSellers";
import { PriceScatter } from "@/components/charts/PriceScatter";
import { DistressedSalesTable } from "@/components/tables/DistressedSalesTable";
import { StaleParcelsTable } from "@/components/tables/StaleParcelsTable";
import { Skeleton } from "@/components/ui/skeleton";

export default function AnalyticsPage() {
  const { filters } = useFilters();
  const { data: txnData, isLoading: txnLoading } = useTransactions({ ...filters, limit: 5_000 });
  const { data: buyers = [], isLoading: buyersLoading } = useTopBuyers(20);
  const { data: sellers = [], isLoading: sellersLoading } = useTopSellers(20);
  const { data: neighborhoods = [], isLoading: nbhdLoading } = useNeighborhoods({
    sale_date__gte: filters.sale_date__gte,
    sale_date__lte: filters.sale_date__lte,
  });
  const { data: trends = [], isLoading: trendsLoading } = useNeighborhoodTrends({ min_transactions: 5 });
  const { data: distressed = [], isLoading: distressedLoading } = useDistressedSales({ limit: 50 });
  const { data: stale = [], isLoading: staleLoading } = useStaleParcels({ limit: 50 });

  const transactions = txnData?.entities ?? [];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Analytics</h1>

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">Neighborhoods</h2>
        {nbhdLoading ? <Skeleton className="h-[340px] rounded-lg" /> : <NeighborhoodRankings data={neighborhoods} />}
      </section>

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">Price Trends by Neighborhood</h2>
        {trendsLoading ? <Skeleton className="h-[340px] rounded-lg" /> : <NeighborhoodTrends data={trends} />}
      </section>

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">Top Buyers & Sellers</h2>
        {buyersLoading || sellersLoading ? (
          <Skeleton className="h-[360px] rounded-lg" />
        ) : (
          <TopBuyersSellers buyers={buyers} sellers={sellers} />
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">Price Timeline</h2>
        {txnLoading ? <Skeleton className="h-[300px] rounded-lg" /> : <PriceScatter transactions={transactions} />}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">Distressed Sales</h2>
          {distressedLoading ? <Skeleton className="h-[300px] rounded-lg" /> : <DistressedSalesTable data={distressed} />}
        </section>

        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">Stale Parcels</h2>
          {staleLoading ? <Skeleton className="h-[300px] rounded-lg" /> : <StaleParcelsTable data={stale} />}
        </section>
      </div>
    </div>
  );
}
