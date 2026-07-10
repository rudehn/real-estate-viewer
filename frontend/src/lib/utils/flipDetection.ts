import type { FlipCandidate, TransactionResponse } from "@/lib/types/api";

export function detectFlips(
  transactions: TransactionResponse[],
  maxHoldDays = 730,
  minProfitPct = 0.1
): FlipCandidate[] {
  // Group by parcel_id
  const byParcel = new Map<string, TransactionResponse[]>();
  for (const t of transactions) {
    if (!byParcel.has(t.parcel_id)) byParcel.set(t.parcel_id, []);
    byParcel.get(t.parcel_id)!.push(t);
  }

  const flips: FlipCandidate[] = [];

  for (const txns of Array.from(byParcel.values())) {
    if (txns.length < 2) continue;
    const sorted = [...txns].sort(
      (a, b) => new Date(a.sale_date).getTime() - new Date(b.sale_date).getTime()
    );

    for (let i = 0; i < sorted.length - 1; i++) {
      const buy = sorted[i];
      const sell = sorted[i + 1];
      if (!buy.sale_price || !sell.sale_price) continue;

      const buyDate = new Date(buy.sale_date + "T00:00:00");
      const sellDate = new Date(sell.sale_date + "T00:00:00");
      const holdDays = Math.round(
        (sellDate.getTime() - buyDate.getTime()) / (1000 * 60 * 60 * 24)
      );

      if (holdDays <= 0 || holdDays > maxHoldDays) continue;

      const profit = sell.sale_price - buy.sale_price;
      const profitPct = profit / buy.sale_price;

      if (profitPct < minProfitPct) continue;

      flips.push({
        parcel_id: buy.parcel_id,
        parcel_location: buy.parcel_location,
        buy_date: buy.sale_date,
        sell_date: sell.sale_date,
        buy_price: buy.sale_price,
        sell_price: sell.sale_price,
        hold_days: holdDays,
        profit,
        profit_pct: profitPct,
        buyer: buy.new_owner,
        seller: sell.old_owner,
      });
    }
  }

  return flips.sort((a, b) => b.profit_pct - a.profit_pct);
}
