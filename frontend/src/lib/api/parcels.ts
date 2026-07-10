import { apiFetch, type ParamValue } from "./client";
import type { ParcelListResponse, TransactionResponse } from "@/lib/types/api";

export async function getParcels(filters: Record<string, ParamValue> = {}): Promise<ParcelListResponse> {
  return apiFetch<ParcelListResponse>("/parcels", filters);
}

export async function getParcelHistory(parcelId: string): Promise<TransactionResponse[]> {
  return apiFetch<TransactionResponse[]>(`/parcels/${encodeURIComponent(parcelId)}/history`);
}
