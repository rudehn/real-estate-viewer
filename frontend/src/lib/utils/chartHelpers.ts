import type { TransactionResponse } from "@/lib/types/api";
import { computeMedian } from "./formatters";

export type Period = "monthly" | "quarterly" | "annual";

export interface PricePeriodPoint {
  period: string;
  median: number;
  count: number;
  total: number;
}

export interface VolumePeriodPoint {
  period: string;
  count: number;
}

function getPeriodKey(date: Date, period: Period): string {
  const y = date.getFullYear();
  const m = date.getMonth() + 1;
  if (period === "annual") return `${y}`;
  if (period === "quarterly") return `${y} Q${Math.ceil(m / 3)}`;
  return `${y}-${String(m).padStart(2, "0")}`;
}

export function groupByPeriod(
  transactions: TransactionResponse[],
  period: Period
): PricePeriodPoint[] {
  const map = new Map<string, number[]>();

  for (const t of transactions) {
    const d = new Date(t.sale_date + "T00:00:00");
    const key = getPeriodKey(d, period);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(t.sale_price);
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([period, prices]) => ({
      period,
      median: computeMedian(prices),
      count: prices.length,
      total: prices.reduce((s, p) => s + p, 0),
    }));
}

export interface SeasonalCell {
  year: number;
  month: number;
  count: number;
}

export function buildSeasonalData(
  transactions: TransactionResponse[]
): SeasonalCell[] {
  const map = new Map<string, number>();
  for (const t of transactions) {
    const d = new Date(t.sale_date + "T00:00:00");
    const key = `${d.getFullYear()}-${d.getMonth() + 1}`;
    map.set(key, (map.get(key) ?? 0) + 1);
  }

  const cells: SeasonalCell[] = [];
  const years = Array.from(new Set(transactions.map((t) => new Date(t.sale_date + "T00:00:00").getFullYear()))).sort();
  for (const year of years) {
    for (let month = 1; month <= 12; month++) {
      cells.push({ year, month, count: map.get(`${year}-${month}`) ?? 0 });
    }
  }
  return cells;
}
