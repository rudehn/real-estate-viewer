"use client";

import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils/formatters";
import { neighborhoodLabel, neighborhoodName } from "@/lib/utils/neighborhoods";
import type { NeighborhoodTrend } from "@/lib/types/api";

interface Props {
  data: NeighborhoodTrend[];
}

const COLORS = [
  "#3b82f6", "#f97316", "#22c55e", "#8b5cf6", "#ec4899",
  "#14b8a6", "#eab308", "#ef4444", "#6366f1", "#84cc16",
];

export function NeighborhoodTrends({ data }: Props) {
  // Pivot: { year -> { neighborhood -> median_price } }
  const neighborhoods = Array.from(new Set(data.map((d) => d.neighborhood)));
  const years = Array.from(new Set(data.map((d) => d.year))).sort();

  const pivoted = years.map((year) => {
    const row: Record<string, number | string> = { year: String(year) };
    for (const nbhd of neighborhoods) {
      const match = data.find((d) => d.year === year && d.neighborhood === nbhd);
      if (match) row[nbhd] = match.median_price;
    }
    return row;
  });

  // Default to the 10 most active neighborhoods: picking by price surfaces
  // tiny luxury subdivisions whose 5-sale medians dwarf everything else.
  const salesByNbhd = new Map<string, number>();
  for (const d of data) {
    salesByNbhd.set(d.neighborhood, (salesByNbhd.get(d.neighborhood) ?? 0) + d.transaction_count);
  }
  const top10 = Array.from(salesByNbhd.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([nbhd]) => nbhd);

  const [selected, setSelected] = useState<string | null>(null);
  const visible = selected ? [selected] : top10;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-medium">Neighborhood Median Price Trends</CardTitle>
          <select
            className="text-xs border rounded px-2 py-1 bg-background"
            value={selected ?? ""}
            onChange={(e) => setSelected(e.target.value || null)}
          >
            <option value="">Top 10 neighborhoods</option>
            {[...neighborhoods]
              .sort((a, b) => neighborhoodName(a).localeCompare(neighborhoodName(b)))
              .map((n) => (
                <option key={n} value={n}>{neighborhoodLabel(n, 40)}</option>
              ))}
          </select>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={pivoted} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="year" tick={{ fontSize: 11 }} />
            <YAxis tickFormatter={(v: number) => formatCurrency(v)} tick={{ fontSize: 11 }} width={60} />
            <Tooltip
              formatter={(v: number, name: string) => [formatCurrency(v), neighborhoodLabel(name, 30)]}
              labelStyle={{ fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 10 }} formatter={(v: string) => neighborhoodLabel(v, 20)} />
            {visible.map((nbhd, i) => (
              <Line
                key={nbhd}
                type="linear"
                dataKey={nbhd}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={1.5}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
