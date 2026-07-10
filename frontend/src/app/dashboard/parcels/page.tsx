"use client";

import { useTransactions } from "@/lib/hooks/useTransactions";
import { useFilters } from "@/lib/hooks/useFilters";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import Link from "next/link";

export default function ParcelsPage() {
  const { filters } = useFilters();
  // Use transactions with parcel data embedded
  const { data, isLoading } = useTransactions({ ...filters, limit: 200 });
  const transactions = data?.entities ?? [];

  // Deduplicate by parcel_id — show the most recent transaction per parcel
  const parcelMap = new Map<string, (typeof transactions)[0]>();
  for (const t of [...transactions].sort((a, b) => b.sale_date.localeCompare(a.sale_date))) {
    if (!parcelMap.has(t.parcel_id)) parcelMap.set(t.parcel_id, t);
  }
  const parcels = Array.from(parcelMap.values());

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Parcels</h1>
      <p className="text-sm text-muted-foreground">
        Showing {parcels.length} unique parcels from current filters
      </p>
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {parcels.map((t) => (
            <Link key={t.parcel_id} href={`/dashboard/parcels/${t.parcel_id}`}>
              <Card className="hover:bg-muted/40 transition-colors cursor-pointer h-full">
                <CardContent className="p-4 space-y-1">
                  <div className="font-medium text-sm truncate">{t.parcel_location}</div>
                  <div className="text-green-700 font-semibold">{formatCurrencyFull(t.sale_price)}</div>
                  <div className="flex gap-2 items-center text-xs text-muted-foreground">
                    <Badge variant="outline" className="text-xs">{t.parcel_class}</Badge>
                    <span>{t.acres.toFixed(2)} ac</span>
                    <span>{formatDate(t.sale_date)}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
