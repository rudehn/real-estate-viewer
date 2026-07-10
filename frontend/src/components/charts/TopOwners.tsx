"use client";

import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/utils/formatters";
import type { OwnerHoldings } from "@/lib/types/api";

type SortKey = "parcel_count" | "total_acres" | "total_assessed_value";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "parcel_count", label: "Properties" },
  { value: "total_acres", label: "Acres" },
  { value: "total_assessed_value", label: "Value" },
];

interface Props {
  data: OwnerHoldings[];
}

export function TopOwners({ data }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>("parcel_count");

  const chartData = [...data]
    .sort((a, b) => b[sortBy] - a[sortBy])
    .slice(0, 15)
    .map((d) => ({
      name: d.owner_name.length > 24 ? d.owner_name.slice(0, 24) + "…" : d.owner_name,
      value: d[sortBy],
      raw: d,
    }));

  const formatValue = (v: number) =>
    sortBy === "parcel_count" ? `${v}` :
    sortBy === "total_acres" ? `${v.toFixed(1)} ac` :
    formatCurrency(v);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-sm font-medium">Current Top Property Owners</CardTitle>
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
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 24, top: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tickFormatter={formatValue} tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={140} />
            <Tooltip
              formatter={(v: number) => [formatValue(v), SORT_OPTIONS.find(o => o.value === sortBy)?.label]}
              labelStyle={{ fontSize: 12 }}
            />
            <Bar dataKey="value" radius={[0, 2, 2, 0]}>
              {chartData.map((_, i) => (
                <Cell key={i} fill={`hsl(${210 + i * 8}, 65%, ${50 + i * 1.5}%)`} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
