"use client";

import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { getTransactions } from "@/lib/api/transactions";
import type { TransactionFilters } from "@/lib/types/api";

export function useTransactions(
  filters: TransactionFilters & { limit?: number } = {},
  options: { enabled?: boolean } = {}
) {
  return useQuery({
    queryKey: ["transactions", filters],
    queryFn: () => getTransactions({ limit: 5000, ...filters }),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  });
}
