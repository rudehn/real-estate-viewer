export type ParcelClass =
  | "Agricultural"
  | "Commercial"
  | "Exempt"
  | "Industrial"
  | "Residential"
  | "Utilities";

export type SaleType =
  | "LAND ONLY"
  | "BUILDING ONLY"
  | "LAND AND BUILDING"
  | "MOBILE HOME";

export interface ParcelResponse {
  parcel_id: string;
  parcel_location: string;
  parcel_class: ParcelClass;
  acres: number;
  latitude: number | null;
  longitude: number | null;
}

export interface TransactionResponse {
  id: number;
  parcel_id: string;
  conv_num: number | null;
  sale_date: string; // ISO date string "2023-01-15"
  sale_price: number;
  old_owner: string;
  new_owner: string;
  parcel_location: string;
  mailing_name: string;
  mailing_address: string;
  parcel_class: ParcelClass;
  acres: number;
  taxable_land: number;
  taxable_building: number;
  taxable_total: number;
  assessed_land: number | null;
  assessed_building: number | null;
  assessed_total: number | null;
  sale_type: SaleType | null;
  sale_validity: string | null;
  deed_reference: string | null;
  neighborhood: string | null;
  parcel: ParcelResponse | null;
}

export interface TransactionListResponse {
  count: number;
  entities: TransactionResponse[];
}

export interface ParcelListResponse {
  count: number;
  entities: ParcelResponse[];
}

export interface OwnerStats {
  owner_name: string;
  transaction_count: number;
  total_spent: number;
  avg_price: number;
}

export interface NeighborhoodStats {
  neighborhood: string;
  transaction_count: number;
  total_volume: number;
  avg_price: number;
  min_price: number;
  max_price: number;
}

export interface TransactionFilters {
  sale_date__gte?: string;
  sale_date__lte?: string;
  sale_price__gte?: number;
  sale_price__lte?: number;
  acres__gte?: number;
  acres__lte?: number;
  parcel_class__in?: ParcelClass[];
  new_owner__ilike?: string;
  is_geocoded?: boolean;
  offset?: number;
  limit?: number;
  order_by?: string[];
}

export interface AnalyticsFilters {
  limit?: number;
  min_transactions?: number;
  sale_date__gte?: string;
  sale_date__lte?: string;
  parcel_class?: ParcelClass;
}

export interface FlipResult {
  parcel_id: string;
  parcel_location: string;
  buy_date: string;
  sell_date: string;
  buy_price: number;
  sell_price: number;
  hold_days: number;
  profit: number;
  profit_pct: number;
  buyer: string;
  seller: string;
}

export interface DistressedSale {
  id: number;
  parcel_id: string;
  parcel_location: string;
  sale_date: string;
  sale_price: number;
  assessed_total: number;
  assessed_ratio: number;
  new_owner: string;
  neighborhood: string | null;
  parcel_class: ParcelClass;
}

export interface OwnerHoldings {
  owner_name: string;
  parcel_count: number;
  total_acres: number;
  total_assessed_value: number;
}

export interface NetSellerStats {
  owner_name: string;
  buy_count: number;
  sell_count: number;
  net: number;
}

export interface NeighborhoodTrend {
  neighborhood: string;
  year: number;
  median_price: number;
  yoy_change_pct: number | null;
}

export interface StaleParcel {
  parcel_id: string;
  parcel_location: string;
  parcel_class: ParcelClass;
  last_sale_date: string;
  last_sale_price: number;
  years_since_sale: number;
}

export interface AcquisitionWave {
  owner_name: string;
  window_start: string;
  window_end: string;
  acquisition_count: number;
  total_spent: number;
}

export interface OwnerParcel {
  parcel_id: string;
  parcel_location: string;
  parcel_class: ParcelClass;
  acres: number;
  last_sale_date: string;
  last_sale_price: number;
  assessed_total: number | null;
  latitude: number | null;
  longitude: number | null;
  /** Parcels acquired in the same conveyance (deal price covers all of them). */
  deal_size: number;
}

export type Granularity = "month" | "quarter" | "year" | "all";

export interface MarketStatsBucket {
  period: string;
  period_start: string;
  transaction_count: number;
  median_price: number;
  avg_price: number;
  total_volume: number;
}

// Derived types
export interface FlipCandidate {
  parcel_id: string;
  parcel_location: string;
  buy_date: string;
  sell_date: string;
  buy_price: number;
  sell_price: number;
  hold_days: number;
  profit: number;
  profit_pct: number;
  buyer: string;
  seller: string;
}
