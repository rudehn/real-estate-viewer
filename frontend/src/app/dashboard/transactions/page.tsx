"use client";

import { useFilters } from "@/lib/hooks/useFilters";
import { useTransactions } from "@/lib/hooks/useTransactions";
import { useFlips } from "@/lib/hooks/useAnalytics";
import { TransactionTable } from "@/components/tables/TransactionTable";
import { FlipsTable } from "@/components/tables/FlipsTable";
import { Skeleton } from "@/components/ui/skeleton";

export default function TransactionsPage() {
  const { filters } = useFilters();
  const { data, isLoading } = useTransactions({ ...filters, limit: 5_000 });
  const { data: flips = [], isLoading: flipsLoading } = useFlips({
    sale_date__gte: filters.sale_date__gte,
    sale_date__lte: filters.sale_date__lte,
    limit: 100,
  });

  const transactions = data?.entities ?? [];
  const totalCount = data?.count ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Transactions</h1>

      {isLoading ? (
        <Skeleton className="h-[400px] rounded-lg" />
      ) : (
        <TransactionTable data={transactions} totalCount={totalCount} />
      )}

      <section>
        <h2 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wide">
          Flip Detection
        </h2>
        {flipsLoading ? (
          <Skeleton className="h-[200px] rounded-lg" />
        ) : (
          <FlipsTable data={flips} />
        )}
      </section>
    </div>
  );
}
