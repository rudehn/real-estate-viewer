"use client";

import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { priceToColor, getMarkerRadius } from "@/lib/utils/colorScale";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { TransactionResponse } from "@/lib/types/api";
import Link from "next/link";

// Montgomery County, OH centroid
const DEFAULT_CENTER: [number, number] = [39.7589, -84.1916];
const DEFAULT_ZOOM = 11;

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
      (t) => t.parcel?.latitude && t.parcel?.longitude
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

export default function PropertyMap({ transactions }: Props) {
  const geocoded = transactions.filter(
    (t) => t.parcel?.latitude != null && t.parcel?.longitude != null
  );

  const prices = geocoded.map((t) => t.sale_price);
  const minPrice = Math.min(...prices, 0);
  const maxPrice = Math.max(...prices, 1);

  return (
    <div className="h-full w-full rounded-lg overflow-hidden border">
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapController transactions={transactions} />
        {geocoded.map((t) => (
          <CircleMarker
            key={t.id}
            center={[t.parcel!.latitude!, t.parcel!.longitude!]}
            radius={getMarkerRadius(t.acres)}
            pathOptions={{
              fillColor: priceToColor(t.sale_price, minPrice, maxPrice),
              fillOpacity: 0.75,
              color: "#fff",
              weight: 0.5,
            }}
          >
            <Popup>
              <div className="text-xs space-y-0.5 min-w-[180px]">
                <div className="font-semibold text-sm">{t.parcel_location}</div>
                <div className="text-green-700 font-medium">{formatCurrencyFull(t.sale_price)}</div>
                <div className="text-gray-500">{formatDate(t.sale_date)}</div>
                <div>{t.new_owner}</div>
                <div className="text-gray-400">{t.parcel_class} · {t.acres.toFixed(2)} ac</div>
                <div className="pt-1">
                  <Link
                    href={`/dashboard/parcels/${t.parcel_id}`}
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
    </div>
  );
}
