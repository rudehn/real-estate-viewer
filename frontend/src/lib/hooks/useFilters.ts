"use client";

import {
  parseAsFloat,
  parseAsInteger,
  parseAsString,
  parseAsArrayOf,
  useQueryStates,
} from "nuqs";
import type { TransactionFilters, ParcelClass } from "@/lib/types/api";

const PARCEL_CLASSES: ParcelClass[] = [
  "Agricultural",
  "Commercial",
  "Exempt",
  "Industrial",
  "Residential",
  "Utilities",
];

const filterParsers = {
  sale_date__gte: parseAsString.withDefault("2010-01-01"),
  sale_date__lte: parseAsString.withDefault(
    new Date().toISOString().slice(0, 10)
  ),
  sale_price__gte: parseAsInteger.withDefault(10_000),
  sale_price__lte: parseAsInteger.withDefault(500_000_000),
  acres__gte: parseAsFloat.withDefault(0),
  acres__lte: parseAsFloat.withDefault(10_000),
  parcel_class__in: parseAsArrayOf(parseAsString).withDefault(["Residential"]),
  new_owner__ilike: parseAsString,
};

export function useFilters() {
  const [filters, setFilters] = useQueryStates(filterParsers);

  const apiFilters: TransactionFilters = {
    ...filters,
    parcel_class__in: filters.parcel_class__in as ParcelClass[],
    new_owner__ilike: filters.new_owner__ilike ?? undefined,
  };

  function resetFilters() {
    void setFilters({
      sale_date__gte: "2010-01-01",
      sale_date__lte: new Date().toISOString().slice(0, 10),
      sale_price__gte: 10_000,
      sale_price__lte: 500_000_000,
      acres__gte: 0,
      acres__lte: 10_000,
      parcel_class__in: ["Residential"],
      new_owner__ilike: null,
    });
  }

  return { filters: apiFilters, rawFilters: filters, setFilters, resetFilters, PARCEL_CLASSES };
}
