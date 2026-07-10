import { apiFetch, type ParamValue } from "./client";
import type {
  AnalyticsFilters, NeighborhoodStats, OwnerStats,
  FlipResult, DistressedSale, OwnerHoldings, NetSellerStats,
  NeighborhoodTrend, StaleParcel, AcquisitionWave, OwnerParcel,
  Granularity, MarketStatsBucket, TransactionFilters,
} from "@/lib/types/api";

export interface MarketStatsParams extends TransactionFilters {
  granularity?: Granularity;
  market_only?: boolean;
}

export async function getMarketStats(
  params: MarketStatsParams = {}
): Promise<MarketStatsBucket[]> {
  return apiFetch<MarketStatsBucket[]>(
    "/analytics/market-stats",
    params as Record<string, ParamValue>
  );
}

export async function getTopBuyers(
  limit = 20,
  minSpent = 0
): Promise<OwnerStats[]> {
  return apiFetch<OwnerStats[]>("/analytics/top-buyers", { limit, min_spent: minSpent });
}

export async function getTopSellers(limit = 20): Promise<OwnerStats[]> {
  return apiFetch<OwnerStats[]>("/analytics/top-sellers", { limit });
}

export async function getNeighborhoods(
  filters: AnalyticsFilters = {}
): Promise<NeighborhoodStats[]> {
  return apiFetch<NeighborhoodStats[]>("/analytics/neighborhoods", filters as Record<string, ParamValue>);
}

export async function getFlips(params: {
  max_hold_days?: number;
  min_profit_pct?: number;
  min_profit?: number;
  sale_date__gte?: string;
  sale_date__lte?: string;
  limit?: number;
} = {}): Promise<FlipResult[]> {
  return apiFetch<FlipResult[]>("/analytics/flips", params as Record<string, ParamValue>);
}

export async function getDistressedSales(params: {
  max_ratio?: number;
  sale_date__gte?: string;
  sale_date__lte?: string;
  parcel_class?: string;
  limit?: number;
} = {}): Promise<DistressedSale[]> {
  return apiFetch<DistressedSale[]>("/analytics/distressed", params as Record<string, ParamValue>);
}

export async function getTopOwners(params: {
  limit?: number;
  order_by?: string;
  parcel_class?: string;
} = {}): Promise<OwnerHoldings[]> {
  return apiFetch<OwnerHoldings[]>("/analytics/top-owners", params as Record<string, ParamValue>);
}

export async function getNetSellers(params: {
  min_net_sells?: number;
  sale_date__gte?: string;
  sale_date__lte?: string;
  limit?: number;
} = {}): Promise<NetSellerStats[]> {
  return apiFetch<NetSellerStats[]>("/analytics/net-sellers", params as Record<string, ParamValue>);
}

export async function getNeighborhoodTrends(params: {
  neighborhood?: string;
  min_transactions?: number;
} = {}): Promise<NeighborhoodTrend[]> {
  return apiFetch<NeighborhoodTrend[]>("/analytics/neighborhoods/trends", params as Record<string, ParamValue>);
}

export async function getStaleParcels(params: {
  min_years?: number;
  parcel_class?: string;
  limit?: number;
} = {}): Promise<StaleParcel[]> {
  return apiFetch<StaleParcel[]>("/analytics/stale-parcels", params as Record<string, ParamValue>);
}

export async function getAcquisitionWaves(params: {
  window_days?: number;
  min_acquisitions?: number;
  sale_date__gte?: string;
  sale_date__lte?: string;
  limit?: number;
} = {}): Promise<AcquisitionWave[]> {
  return apiFetch<AcquisitionWave[]>("/analytics/acquisition-waves", params as Record<string, ParamValue>);
}

export async function getAbsenteeOwners(params: {
  parcel_class?: string;
  limit?: number;
} = {}): Promise<OwnerStats[]> {
  return apiFetch<OwnerStats[]>("/analytics/absentee-owners", params as Record<string, ParamValue>);
}

export async function searchOwners(q: string, limit = 10): Promise<string[]> {
  return apiFetch<string[]>("/analytics/owner-search", { q, limit });
}

export async function getOwnerHoldings(owner_name: string): Promise<OwnerParcel[]> {
  return apiFetch<OwnerParcel[]>("/analytics/owner-holdings", { owner_name });
}
