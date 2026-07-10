"use client";

import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useTheme } from "next-themes";
import "leaflet/dist/leaflet.css";
import {
  PRICE_COLORS,
  PRICE_COLORS_DARK,
  computeQuantileBreaks,
  getMarkerRadius,
  priceToQuantileColor,
} from "@/lib/utils/colorScale";
import { formatCurrency, formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { TransactionResponse } from "@/lib/types/api";
import Link from "next/link";

// Montgomery County, OH centroid
const DEFAULT_CENTER: [number, number] = [39.7589, -84.1916];
const DEFAULT_ZOOM = 11;

// Generous bounding box around Montgomery County. The Census geocoder
// occasionally mismatches an address hundreds of miles away; every parcel
// is in this county, so anything outside the box is a geocoding error and
// would both mislead and blow up the auto-fit zoom.
const COUNTY_BOUNDS = { latMin: 39.4, latMax: 40.1, lonMin: -84.9, lonMax: -83.8 };

function inCounty(lat: number, lon: number): boolean {
  return (
    lat >= COUNTY_BOUNDS.latMin && lat <= COUNTY_BOUNDS.latMax &&
    lon >= COUNTY_BOUNDS.lonMin && lon <= COUNTY_BOUNDS.lonMax
  );
}

interface Props {
  transactions: TransactionResponse[];
}

// Re-center map when transactions change
function MapController({ transactions }: { transactions: TransactionResponse[] }) {
  const map = useMap();
  const hasFlown = useRef(false);

  useEffect(() => {
    if (hasFlown.current || transactions.length === 0) return;
    const geocoded = transactions.filter(
      (t) =>
        t.parcel?.latitude &&
        t.parcel?.longitude &&
        inCounty(t.parcel.latitude, t.parcel.longitude)
    );
    if (geocoded.length === 0) return;
    const lats = geocoded.map((t) => t.parcel!.latitude!);
    const lons = geocoded.map((t) => t.parcel!.longitude!);
    const bounds: [[number, number], [number, number]] = [
      [Math.min(...lats), Math.min(...lons)],
      [Math.max(...lats), Math.max(...lons)],
    ];
    map.fitBounds(bounds, { padding: [30, 30] });
    hasFlown.current = true;
  }, [map, transactions]);

  return null;
}

function PriceLegend({ breaks, colors }: { breaks: number[]; colors: string[] }) {
  if (breaks.length === 0) return null;
  const labels = [
    `< ${formatCurrency(breaks[0])}`,
    ...breaks.slice(1).map((b, i) => `${formatCurrency(breaks[i])}–${formatCurrency(b)}`),
    `> ${formatCurrency(breaks[breaks.length - 1])}`,
  ];
  return (
    <div className="absolute bottom-4 right-3 z-[1000] bg-background/90 border rounded-md shadow px-3 py-2 text-xs space-y-1">
      <div className="font-medium mb-1">Sale price (quintiles)</div>
      {labels.map((label, i) => (
        <div key={i} className="flex items-center gap-2">
          <span
            className="inline-block w-3 h-3 rounded-full border border-foreground/20"
            style={{ backgroundColor: colors[i] }}
          />
          <span className="text-muted-foreground">{label}</span>
        </div>
      ))}
      <div className="text-muted-foreground pt-1 border-t mt-1">Circle size = acreage</div>
    </div>
  );
}

export default function PropertyMap({ transactions }: Props) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const geocoded = useMemo(
    () =>
      transactions.filter(
        (t) =>
          t.parcel?.latitude != null &&
          t.parcel?.longitude != null &&
          inCounty(t.parcel.latitude, t.parcel.longitude)
      ),
    [transactions]
  );

  const breaks = useMemo(
    () => computeQuantileBreaks(geocoded.map((t) => t.sale_price)),
    [geocoded]
  );
  const colors = isDark ? PRICE_COLORS_DARK : PRICE_COLORS;

  return (
    <div className="relative h-full w-full rounded-lg overflow-hidden border">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        style={{ height: "100%", width: "100%" }}
        preferCanvas
      >
        <TileLayer
          key={isDark ? "dark" : "light"}
          attribution={
            isDark
              ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
              : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          }
          url={
            isDark
              ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          }
        />
        <MapController transactions={transactions} />
        {geocoded.map((t) => (
          <CircleMarker
            key={t.id}
            center={[t.parcel!.latitude!, t.parcel!.longitude!]}
            radius={getMarkerRadius(t.acres)}
            pathOptions={{
              fillColor: priceToQuantileColor(t.sale_price, breaks, colors),
              fillOpacity: 0.8,
              color: isDark ? "#0f172a" : "#fff",
              weight: 0.5,
            }}
          >
            <Popup>
              <div className="text-xs space-y-0.5 min-w-[180px]">
                <div className="font-semibold text-sm">{t.parcel_location}</div>
                <div className="text-green-700 font-medium">{formatCurrencyFull(t.sale_price)}</div>
                <div className="text-gray-500">{formatDate(t.sale_date)}</div>
                <div>{t.new_owner}</div>
                <div className="text-gray-400">
                  {t.parcel_class}
                  {t.acres > 0 && ` · ${t.acres.toFixed(2)} ac`}
                </div>
                <div className="pt-1">
                  <Link
                    href={`/dashboard/parcels/${encodeURIComponent(t.parcel_id)}`}
                    className="text-blue-600 underline"
                  >
                    View parcel history →
                  </Link>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      <PriceLegend breaks={breaks} colors={colors} />
    </div>
  );
}
