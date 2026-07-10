"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { StaleParcel } from "@/lib/types/api";
import Link from "next/link";

interface Props {
  data: StaleParcel[];
}

// County sales records begin in January 2001; a "last sale" that early
// really means no sale in the dataset's lifetime.
const DATASET_START_YEAR = 2001;

export function StaleParcelsTable({ data }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Stale Parcels — {data.length} found
          <span className="text-muted-foreground font-normal ml-2 text-xs">(not sold in 10+ years)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              <tr>
                {["Address", "Class", "Last Sale", "Last Price", "Years Held"].map((h) => (
                  <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.parcel_id} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-3 py-1.5">
                    <Link href={`/dashboard/parcels/${row.parcel_id}`} className="text-blue-600 hover:underline max-w-[200px] block truncate">
                      {row.parcel_location}
                    </Link>
                  </td>
                  <td className="px-3 py-1.5">
                    <Badge variant="outline" className="text-xs">{row.parcel_class}</Badge>
                  </td>
                  <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(row.last_sale_date)}</td>
                  <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(row.last_sale_price)}</td>
                  <td className="px-3 py-1.5 tabular-nums font-medium whitespace-nowrap">
                    {new Date(row.last_sale_date).getFullYear() <= DATASET_START_YEAR
                      ? "25+ yrs*"
                      : `${row.years_since_sale.toFixed(1)} yrs`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground px-3 py-2">
          * Records begin in 2001; these parcels have no sale in the dataset&apos;s lifetime.
        </p>
      </CardContent>
    </Card>
  );
}
