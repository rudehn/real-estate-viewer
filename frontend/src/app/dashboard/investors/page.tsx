"use client";

import { useState } from "react";
import { useTopOwners, useNetSellers, useAcquisitionWaves, useAbsenteeOwners } from "@/lib/hooks/useAnalytics";
import { TopOwners } from "@/components/charts/TopOwners";
import { NetSellersTable, AcquisitionWavesTable, AbsenteeOwnersTable } from "@/components/tables/InvestorTables";
import { Skeleton } from "@/components/ui/skeleton";

export default function InvestorsPage() {
  const [orderBy] = useState("count");

  const { data: owners = [], isLoading: ownersLoading } = useTopOwners({ limit: 20, order_by: orderBy });
  const { data: netSellers = [], isLoading: netLoading } = useNetSellers({ limit: 50 });
  const { data: waves = [], isLoading: wavesLoading } = useAcquisitionWaves({ limit: 50 });
  const { data: absentee = [], isLoading: absenteeLoading } = useAbsenteeOwners({ limit: 50 });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Investor Intelligence</h1>

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
          Current Top Owners
        </h2>
        {ownersLoading ? (
          <Skeleton className="h-[360px] rounded-lg" />
        ) : (
          <TopOwners data={owners} />
        )}
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
            Acquisition Waves
          </h2>
          {wavesLoading ? (
            <Skeleton className="h-[300px] rounded-lg" />
          ) : (
            <AcquisitionWavesTable data={waves} />
          )}
        </section>

        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
            Net Sellers
          </h2>
          {netLoading ? (
            <Skeleton className="h-[300px] rounded-lg" />
          ) : (
            <NetSellersTable data={netSellers} />
          )}
        </section>
      </div>

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
          Absentee Owners
        </h2>
        {absenteeLoading ? (
          <Skeleton className="h-[300px] rounded-lg" />
        ) : (
          <AbsenteeOwnersTable data={absentee} />
        )}
      </section>
    </div>
  );
}
