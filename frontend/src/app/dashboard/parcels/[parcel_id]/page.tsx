"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { getParcelHistory } from "@/lib/api/parcels";
import { useParcelComps } from "@/lib/hooks/useAnalytics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { OwnerLink } from "@/components/OwnerLink";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import { neighborhoodName } from "@/lib/utils/neighborhoods";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import Link from "next/link";

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

function StreetView({
  lat, lng, address,
}: {
  lat: number | null | undefined;
  lng: number | null | undefined;
  address: string;
}) {
  const query = lat && lng ? `${lat},${lng}` : address;
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;

  if (MAPS_KEY && lat && lng) {
    const src = `https://maps.googleapis.com/maps/api/streetview?size=800x300&location=${lat},${lng}&key=${MAPS_KEY}`;
    return (
      <a href={mapsUrl} target="_blank" rel="noreferrer">
        <img src={src} alt={`Street view of ${address}`}
          className="w-full rounded-lg object-cover h-[220px] bg-muted" />
      </a>
    );
  }

  return (
    <a href={mapsUrl} target="_blank" rel="noreferrer"
      className="block text-sm text-primary hover:underline">
      View on Google Maps ↗
    </a>
  );
}

export default function ParcelDetailPage() {
  const { parcel_id } = useParams<{ parcel_id: string }>();
  const parcelId = decodeURIComponent(parcel_id);

  const { data: history = [], isLoading } = useQuery({
    queryKey: ["parcel-history", parcelId],
    queryFn: () => getParcelHistory(parcelId),
  });
  const { data: comps } = useParcelComps(parcelId);

  const sorted = [...history].sort((a, b) => a.sale_date.localeCompare(b.sale_date));
  const latest = sorted[sorted.length - 1];

  const chartData = sorted.map((t) => ({
    date: t.sale_date,
    price: t.sale_price,
    label: formatDate(t.sale_date),
  }));

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex items-center gap-3">
        <Link href="/dashboard/parcels" className="text-sm text-muted-foreground hover:text-foreground">
          ← Parcels
        </Link>
      </div>

      {isLoading ? (
        <Skeleton className="h-32 rounded-lg" />
      ) : latest ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>{latest.parcel_location}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3 text-sm">
            <Badge variant="secondary">{latest.parcel_class}</Badge>
            <span>{latest.acres.toFixed(2)} acres</span>
            <span className="text-muted-foreground">Parcel ID: {parcelId}</span>
            {latest.neighborhood && (
              <span className="text-muted-foreground" title={latest.neighborhood}>
                Neighborhood: {neighborhoodName(latest.neighborhood)}
              </span>
            )}
          </CardContent>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">Parcel not found.</p>
      )}

      {/* Street view / Google Maps link */}
      {!isLoading && latest && (
        <Card>
          <CardContent className="p-3">
            <StreetView
              lat={latest.parcel?.latitude}
              lng={latest.parcel?.longitude}
              address={latest.parcel_location}
            />
          </CardContent>
        </Card>
      )}

      {/* Price history chart */}
      {!isLoading && sorted.length > 1 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Sale Price History</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis
                  tickFormatter={(v) => formatCurrencyFull(v)}
                  tick={{ fontSize: 10 }}
                  width={80}
                />
                <Tooltip
                  formatter={(v: number) => [formatCurrencyFull(v), "Sale Price"]}
                />
                <Line
                  type="linear"
                  dataKey="price"
                  stroke="hsl(var(--chart-1))"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Comparable sales */}
      {comps && comps.comps.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Comparable Sales
              <span className="text-muted-foreground font-normal ml-2 text-xs">
                (recent market sales · same neighborhood &amp; class
                {comps.median_price ? ` · median ${formatCurrencyFull(comps.median_price)}` : ""})
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 border-b">
                <tr>
                  {["Address", "Date", "Sale Price", "Acres"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comps.comps.map((c) => (
                  <tr key={`${c.parcel_id}-${c.sale_date}`} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-1.5">
                      <Link
                        href={`/dashboard/parcels/${encodeURIComponent(c.parcel_id)}`}
                        className="text-primary hover:underline"
                      >
                        {c.parcel_location}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(c.sale_date)}</td>
                    <td className="px-3 py-1.5 font-medium tabular-nums">
                      {formatCurrencyFull(c.sale_price)}
                    </td>
                    <td className="px-3 py-1.5 tabular-nums">
                      {c.acres > 0 ? c.acres.toFixed(2) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Transaction history table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Sale History ({sorted.length} transaction{sorted.length !== 1 ? "s" : ""})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4">
              <Skeleton className="h-24" />
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="bg-muted/50 border-b">
                <tr>
                  {["Date", "Sale Price", "Buyer", "Seller", "Class", "Acres"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.reverse().map((t) => (
                  <tr key={t.id} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(t.sale_date)}</td>
                    <td className="px-3 py-1.5 font-medium tabular-nums">
                      {formatCurrencyFull(t.sale_price)}
                    </td>
                    <td className="px-3 py-1.5 max-w-[120px] truncate">
                      <OwnerLink name={t.new_owner} />
                    </td>
                    <td className="px-3 py-1.5 max-w-[120px] truncate">
                      <OwnerLink name={t.old_owner} />
                    </td>
                    <td className="px-3 py-1.5">
                      <Badge variant="outline" className="text-xs">{t.parcel_class}</Badge>
                    </td>
                    <td className="px-3 py-1.5">{t.acres.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
