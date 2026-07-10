"use client";

import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/utils/formatters";
import type { NeighborhoodStats } from "@/lib/types/api";

type SortKey = "transaction_count" | "avg_price" | "total_volume";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "transaction_count", label: "Volume" },
  { value: "avg_price", label: "Avg $" },
  { value: "total_volume", label: "Total $" },
];

interface Props {
  data: NeighborhoodStats[];
}

export function NeighborhoodRankings({ data }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>("transaction_count");

  const sorted = [...data].sort((a, b) => b[sortBy] - a[sortBy]).slice(0, 20);
  const formatY = (v: number) => (sortBy === "transaction_count" ? `${v}` : formatCurrency(v));

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-medium">Neighborhood Rankings</CardTitle>
          <div className="flex rounded-md border overflow-hidden text-xs">
            {SORT_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setSortBy(opt.value)}
                className={cn(
                  "px-2 py-1 transition-colors",
                  sortBy === opt.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:bg-muted"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* Keyed on the metric so switching remounts the chart; Recharts
            otherwise leaves the previous axis labels behind. */}
        <ResponsiveContainer key={sortBy} width="100%" height={420}>
          <BarChart data={sorted} layout="vertical" margin={{ left: 12, right: 20, top: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tickFormatter={formatY} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="neighborhood" tick={{ fontSize: 10 }} width={70} interval={0} />
            <Tooltip
              formatter={(v: number) => [formatY(v), sortBy.replace(/_/g, " ")]}
              labelStyle={{ fontSize: 12 }}
            />
            <Bar dataKey={sortBy} radius={[0, 2, 2, 0]} isAnimationActive={false}>
              {sorted.map((_, i) => (
                <Cell key={i} fill={`hsl(${220 - i * 6}, 70%, ${55 + i * 1.5}%)`} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
