"use client";

import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { OwnerParcel } from "@/lib/types/api";
import Link from "next/link";

const DEFAULT_CENTER: [number, number] = [39.7589, -84.1916];

// Same generous county box as PropertyMap: geocoding errors elsewhere in
// the country would wreck the auto-fit zoom.
function inCounty(lat: number, lon: number): boolean {
  return lat >= 39.4 && lat <= 40.1 && lon >= -84.9 && lon <= -83.8;
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const hasFlown = useRef(false);
  useEffect(() => {
    if (hasFlown.current || points.length === 0) return;
    const lats = points.map((p) => p[0]);
    const lons = points.map((p) => p[1]);
    map.fitBounds(
      [
        [Math.min(...lats), Math.min(...lons)],
        [Math.max(...lats), Math.max(...lons)],
      ],
      { padding: [24, 24], maxZoom: 14 }
    );
    hasFlown.current = true;
  }, [map, points]);
  return null;
}

export default function HoldingsMap({ holdings }: { holdings: OwnerParcel[] }) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  const located = useMemo(
    () =>
      holdings.filter(
        (p) => p.latitude != null && p.longitude != null && inCounty(p.latitude, p.longitude)
      ),
    [holdings]
  );

  if (located.length === 0) {
    return (
      <div className="h-full w-full rounded-lg border flex items-center justify-center text-sm text-muted-foreground">
        No geocoded holdings to map.
      </div>
    );
  }

  return (
    <div className="h-full w-full rounded-lg overflow-hidden border">
      <MapContainer center={DEFAULT_CENTER} zoom={11} style={{ height: "100%", width: "100%" }} preferCanvas>
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
        <FitBounds points={located.map((p) => [p.latitude!, p.longitude!])} />
        {located.map((p) => (
          <CircleMarker
            key={p.parcel_id}
            center={[p.latitude!, p.longitude!]}
            radius={5}
            pathOptions={{
              fillColor: isDark ? "#93c5fd" : "#1d4ed8",
              fillOpacity: 0.85,
              color: isDark ? "#0f172a" : "#fff",
              weight: 0.5,
            }}
          >
            <Popup>
              <div className="text-xs space-y-0.5 min-w-[160px]">
                <div className="font-semibold">{p.parcel_location}</div>
                <div>{formatCurrencyFull(p.last_sale_price)} · {formatDate(p.last_sale_date)}</div>
                <Link
                  href={`/dashboard/parcels/${encodeURIComponent(p.parcel_id)}`}
                  className="text-blue-600 underline"
                >
                  View parcel →
                </Link>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
