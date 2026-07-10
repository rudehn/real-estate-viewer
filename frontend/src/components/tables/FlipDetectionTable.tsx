"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { detectFlips } from "@/lib/utils/flipDetection";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { TransactionResponse } from "@/lib/types/api";
import Link from "next/link";

interface Props {
  transactions: TransactionResponse[];
}

export function FlipDetectionTable({ transactions }: Props) {
  const flips = detectFlips(transactions, 730, 0.1);

  if (flips.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Flip Detection</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No flips detected (bought and resold within 2 years with ≥10% profit) in the current
            dataset.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Flip Detection — {flips.length} candidate{flips.length !== 1 ? "s" : ""}
          <span className="text-muted-foreground font-normal ml-2 text-xs">
            (resold within 2 years, ≥10% profit)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              <tr>
                {["Address", "Buy Date", "Sell Date", "Hold", "Buy $", "Sell $", "Profit", "Buyer"].map(
                  (h) => (
                    <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {flips.slice(0, 50).map((flip, i) => (
                <tr key={i} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-1.5">
                    <Link
                      href={`/dashboard/parcels/${flip.parcel_id}`}
                      className="text-blue-600 hover:underline max-w-[160px] block truncate"
                    >
                      {flip.parcel_location}
                    </Link>
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(flip.buy_date)}</td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(flip.sell_date)}</td>
                  <td className="px-3 py-1.5">{flip.hold_days}d</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(flip.buy_price)}</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(flip.sell_price)}</td>
                  <td className="px-3 py-1.5">
                    <Badge variant="default" className="text-xs">
                      +{(flip.profit_pct * 100).toFixed(0)}%
                    </Badge>
                  </td>
                  <td className="px-3 py-1.5 max-w-[120px] truncate">{flip.buyer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
