"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { DistressedSale } from "@/lib/types/api";
import Link from "next/link";

interface Props {
  data: DistressedSale[];
}

export function DistressedSalesTable({ data }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Distressed Sales — {data.length} found
          <span className="text-muted-foreground font-normal ml-2 text-xs">(sold at &lt;70% of assessed value)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              <tr>
                {["Address", "Sale Date", "Sale $", "Assessed $", "Ratio", "Buyer", "Nbhd"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.id} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-1.5">
                    <Link href={`/dashboard/parcels/${row.parcel_id}`} className="text-blue-600 hover:underline max-w-[160px] block truncate">
                      {row.parcel_location}
                    </Link>
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(row.sale_date)}</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(row.sale_price)}</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(row.assessed_total)}</td>
                  <td className="px-3 py-1.5">
                    <Badge variant="destructive" className="text-xs">
                      {(row.assessed_ratio * 100).toFixed(0)}%
                    </Badge>
                  </td>
                  <td className="px-3 py-1.5 max-w-[140px] truncate">{row.new_owner}</td>
                  <td className="px-3 py-1.5">{row.neighborhood ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
