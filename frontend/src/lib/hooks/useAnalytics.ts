"use client";

import { useQuery } from "@tanstack/react-query";
import {
  getTopBuyers, getTopSellers, getNeighborhoods,
  getFlips, getDistressedSales, getTopOwners, getNetSellers,
  getNeighborhoodTrends, getStaleParcels, getAcquisitionWaves, getAbsenteeOwners,
  searchOwners, getOwnerHoldings, getMarketStats, type MarketStatsParams,
} from "@/lib/api/analytics";
import type { AnalyticsFilters } from "@/lib/types/api";

const STALE = 5 * 60_000;

export function useMarketStats(params: MarketStatsParams = {}) {
  return useQuery({
    queryKey: ["market-stats", params],
    queryFn: () => getMarketStats(params),
    staleTime: STALE,
  });
}

export function useTopBuyers(limit = 20) {
  return useQuery({ queryKey: ["top-buyers", limit], queryFn: () => getTopBuyers(limit), staleTime: STALE });
}

export function useTopSellers(limit = 20) {
  return useQuery({ queryKey: ["top-sellers", limit], queryFn: () => getTopSellers(limit), staleTime: STALE });
}

export function useNeighborhoods(filters: AnalyticsFilters = {}) {
  return useQuery({
    queryKey: ["neighborhoods", filters],
    queryFn: () => getNeighborhoods({ limit: 50, min_transactions: 5, ...filters }),
    staleTime: STALE,
  });
}

export function useFlips(params: Parameters<typeof getFlips>[0] = {}) {
  return useQuery({ queryKey: ["flips", params], queryFn: () => getFlips(params), staleTime: STALE });
}

export function useDistressedSales(params: Parameters<typeof getDistressedSales>[0] = {}) {
  return useQuery({ queryKey: ["distressed", params], queryFn: () => getDistressedSales(params), staleTime: STALE });
}

export function useTopOwners(params: Parameters<typeof getTopOwners>[0] = {}) {
  return useQuery({ queryKey: ["top-owners", params], queryFn: () => getTopOwners(params), staleTime: STALE });
}

export function useNetSellers(params: Parameters<typeof getNetSellers>[0] = {}) {
  return useQuery({ queryKey: ["net-sellers", params], queryFn: () => getNetSellers(params), staleTime: STALE });
}

export function useNeighborhoodTrends(params: Parameters<typeof getNeighborhoodTrends>[0] = {}) {
  return useQuery({ queryKey: ["nbhd-trends", params], queryFn: () => getNeighborhoodTrends(params), staleTime: STALE });
}

export function useStaleParcels(params: Parameters<typeof getStaleParcels>[0] = {}) {
  return useQuery({ queryKey: ["stale-parcels", params], queryFn: () => getStaleParcels(params), staleTime: STALE });
}

export function useAcquisitionWaves(params: Parameters<typeof getAcquisitionWaves>[0] = {}) {
  return useQuery({ queryKey: ["acquisition-waves", params], queryFn: () => getAcquisitionWaves(params), staleTime: STALE });
}

export function useAbsenteeOwners(params: Parameters<typeof getAbsenteeOwners>[0] = {}) {
  return useQuery({ queryKey: ["absentee-owners", params], queryFn: () => getAbsenteeOwners(params), staleTime: STALE });
}

export function useOwnerSearch(q: string) {
  return useQuery({
    queryKey: ["owner-search", q],
    queryFn: () => searchOwners(q),
    enabled: q.trim().length >= 2,
    staleTime: STALE,
  });
}

export function useOwnerHoldings(ownerName: string | null) {
  return useQuery({
    queryKey: ["owner-holdings", ownerName],
    queryFn: () => getOwnerHoldings(ownerName!),
    enabled: !!ownerName,
    staleTime: STALE,
  });
}
