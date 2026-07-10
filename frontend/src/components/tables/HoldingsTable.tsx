"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { OwnerParcel } from "@/lib/types/api";

interface Props {
  holdings: OwnerParcel[];
  title?: string;
}

export function HoldingsTable({ holdings, title = "Current Holdings" }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          {title} ({holdings.length.toLocaleString()})
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {holdings.length === 0 ? (
          <p className="text-sm text-muted-foreground p-4">No current holdings found.</p>
        ) : (
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 border-b sticky top-0">
                <tr>
                  {["Address", "Class", "Acres", "Last Sale", "Last Price", "Assessed"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {holdings.map((p) => (
                  <tr key={p.parcel_id} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-1.5">
                      <Link
                        href={`/dashboard/parcels/${encodeURIComponent(p.parcel_id)}`}
                        className="text-primary hover:underline"
                      >
                        {p.parcel_location}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5">
                      <Badge variant="outline" className="text-xs">{p.parcel_class}</Badge>
                    </td>
                    <td className="px-3 py-1.5 tabular-nums">
                      {p.acres > 0 ? p.acres.toFixed(2) : "—"}
                    </td>
                    <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(p.last_sale_date)}</td>
                    <td className="px-3 py-1.5 tabular-nums whitespace-nowrap">
                      {formatCurrencyFull(p.last_sale_price)}
                      {p.deal_size > 1 && (
                        <span
                          className="ml-1 text-muted-foreground"
                          title={`Acquired in one ${p.deal_size}-parcel deal; the price covers all ${p.deal_size} parcels.`}
                        >
                          ({p.deal_size}-parcel deal)
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 tabular-nums">
                      {p.assessed_total ? formatCurrencyFull(p.assessed_total) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
