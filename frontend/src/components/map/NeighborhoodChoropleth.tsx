"use client";

import { useMemo, useState } from "react";
import { MapContainer, TileLayer, GeoJSON } from "react-leaflet";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import type { Feature } from "geojson";
import type { Layer, PathOptions } from "leaflet";
import "leaflet/dist/leaflet.css";
import { cn } from "@/lib/utils";
import {
  PRICE_COLORS,
  PRICE_COLORS_DARK,
  computeQuantileBreaks,
  priceToQuantileColor,
} from "@/lib/utils/colorScale";
import { formatCurrency } from "@/lib/utils/formatters";
import { useNeighborhoods } from "@/lib/hooks/useAnalytics";
import type { NeighborhoodStats } from "@/lib/types/api";

const DEFAULT_CENTER: [number, number] = [39.7589, -84.1916];

type MetricKey = "median_price" | "transaction_count" | "total_volume";

const METRICS: { value: MetricKey; label: string; format: (v: number) => string }[] = [
  { value: "median_price", label: "Median $", format: formatCurrency },
  { value: "transaction_count", label: "Sales", format: (v) => v.toLocaleString() },
  { value: "total_volume", label: "Total $", format: formatCurrency },
];

interface Props {
  sale_date__gte?: string;
  sale_date__lte?: string;
}

export default function NeighborhoodChoropleth({ sale_date__gte, sale_date__lte }: Props) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const [metric, setMetric] = useState<MetricKey>("median_price");
  const metricDef = METRICS.find((m) => m.value === metric)!;

  const { data: geojson } = useQuery({
    queryKey: ["neighborhoods-geojson"],
    queryFn: async () => {
      const res = await fetch("/neighborhoods.geojson");
      if (!res.ok) throw new Error("Failed to load neighborhood boundaries");
      return res.json() as Promise<GeoJSON.FeatureCollection>;
    },
    staleTime: Infinity,
  });

  const { data: stats = [] } = useNeighborhoods({
    limit: 2_000,
    min_transactions: 3,
    sale_date__gte,
    sale_date__lte,
  });

  const statsByCode = useMemo(() => {
    const m = new Map<string, NeighborhoodStats>();
    for (const s of stats) m.set(s.neighborhood, s);
    return m;
  }, [stats]);

  const breaks = useMemo(
    () => computeQuantileBreaks(stats.map((s) => s[metric]).filter((v) => v > 0)),
    [stats, metric]
  );
  const colors = isDark ? PRICE_COLORS_DARK : PRICE_COLORS;

  const styleFeature = (feature?: Feature): PathOptions => {
    const code = feature?.properties?.code as string | undefined;
    const s = code ? statsByCode.get(code) : undefined;
    if (!s) {
      return {
        fillColor: isDark ? "#1e293b" : "#e2e8f0",
        fillOpacity: 0.25,
        color: isDark ? "#334155" : "#cbd5e1",
        weight: 0.5,
      };
    }
    return {
      fillColor: priceToQuantileColor(s[metric], breaks, colors),
      fillOpacity: 0.65,
      color: isDark ? "#0f172a" : "#fff",
      weight: 0.7,
    };
  };

  const onEachFeature = (feature: Feature, layer: Layer) => {
    const { code, name } = (feature.properties ?? {}) as { code?: string; name?: string };
    const s = code ? statsByCode.get(code) : undefined;
    const body = s
      ? `Median ${formatCurrency(s.median_price)} · ${s.transaction_count.toLocaleString()} sales` +
        `<br/>Total volume ${formatCurrency(s.total_volume)}`
      : "No market sales in range";
    layer.bindTooltip(
      `<strong>${name ?? code ?? "?"}</strong><br/>${body}`,
      { sticky: true }
    );
  };

  const labels =
    breaks.length > 0
      ? [
          `< ${metricDef.format(breaks[0])}`,
          ...breaks.slice(1).map((b, i) => `${metricDef.format(breaks[i])}–${metricDef.format(b)}`),
          `> ${metricDef.format(breaks[breaks.length - 1])}`,
        ]
      : [];

  return (
    <div className="relative h-full w-full rounded-lg overflow-hidden border">
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
        {geojson && (
          <GeoJSON
            // Remount when the join inputs change: leaflet styles are set at add time.
            key={`${metric}-${isDark}-${stats.length}`}
            data={geojson}
            style={styleFeature}
            onEachFeature={onEachFeature}
          />
        )}
      </MapContainer>

      {/* Metric toggle */}
      <div className="absolute top-3 right-3 z-[1000] flex rounded-md border overflow-hidden text-xs bg-background/90 shadow">
        {METRICS.map((m) => (
          <button
            key={m.value}
            onClick={() => setMetric(m.value)}
            className={cn(
              "px-2 py-1 transition-colors",
              metric === m.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* Legend */}
      {labels.length > 0 && (
        <div className="absolute bottom-4 right-3 z-[1000] bg-background/90 border rounded-md shadow px-3 py-2 text-xs space-y-1">
          <div className="font-medium mb-1">{metricDef.label} (quintiles)</div>
          {labels.map((label, i) => (
            <div key={i} className="flex items-center gap-2">
              <span
                className="inline-block w-3 h-3 rounded-sm border border-foreground/20"
                style={{ backgroundColor: colors[i] }}
              />
              <span className="text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
