"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { OwnerLink } from "@/components/OwnerLink";
import { formatCurrency, formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { NetSellerStats, AcquisitionWave, OwnerStats } from "@/lib/types/api";

// --- Net Sellers ---

interface NetSellersProps { data: NetSellerStats[] }

export function NetSellersTable({ data }: NetSellersProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Net Sellers
          <span className="text-muted-foreground font-normal ml-2 text-xs">(selling far more than buying)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              <tr>
                {["Owner", "Buys", "Sells", "Net Sells"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.owner_name} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-1.5 max-w-[200px] truncate font-medium">
                    <OwnerLink name={row.owner_name} />
                  </td>
                  <td className="px-3 py-1.5 tabular-nums">{row.buy_count}</td>
                  <td className="px-3 py-1.5 tabular-nums">{row.sell_count}</td>
                  <td className="px-3 py-1.5">
                    <Badge variant="destructive" className="text-xs">−{row.net}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Acquisition Waves ---

interface WavesProps { data: AcquisitionWave[] }

export function AcquisitionWavesTable({ data }: WavesProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Acquisition Waves
          <span className="text-muted-foreground font-normal ml-2 text-xs">(5+ purchases within 90 days)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              <tr>
                {["Owner", "Window Start", "Window End", "Properties", "Total Spent"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={i} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-1.5 max-w-[180px] truncate font-medium">
                    <OwnerLink name={row.owner_name} />
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(row.window_start)}</td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(row.window_end)}</td>
                  <td className="px-3 py-1.5">
                    <Badge className="text-xs">{row.acquisition_count.toLocaleString()}</Badge>
                  </td>
                  <td className="px-3 py-1.5 tabular-nums whitespace-nowrap">
                    {row.total_spent > 0 ? (
                      formatCurrency(row.total_spent)
                    ) : (
                      <span className="text-muted-foreground">$0 (recorded transfers)</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Absentee Owners ---

interface AbsenteeProps { data: OwnerStats[] }

export function AbsenteeOwnersTable({ data }: AbsenteeProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Absentee Owners
          <span className="text-muted-foreground font-normal ml-2 text-xs">(out-of-state mailing address)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              <tr>
                {["Owner", "Properties", "Total Spent", "Avg Price"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.owner_name} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-1.5 max-w-[200px] truncate font-medium">
                    <OwnerLink name={row.owner_name} />
                  </td>
                  <td className="px-3 py-1.5 tabular-nums">{row.transaction_count}</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(row.total_spent)}</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(row.avg_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
