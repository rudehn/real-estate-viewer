import { apiFetch, type ParamValue } from "./client";
import type {
  TransactionFilters,
  TransactionListResponse,
  TransactionResponse,
} from "@/lib/types/api";

export async function getTransactions(
  filters: TransactionFilters = {}
): Promise<TransactionListResponse> {
  return apiFetch<TransactionListResponse>("/transactions", filters as Record<string, ParamValue>);
}

export async function getTransaction(id: number): Promise<TransactionResponse> {
  return apiFetch<TransactionResponse>(`/transactions/${id}`);
}
