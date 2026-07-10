"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PeriodToggle } from "./PeriodToggle";
import { formatCurrency } from "@/lib/utils/formatters";
import type { Granularity, MarketStatsBucket } from "@/lib/types/api";

interface Props {
  data: MarketStatsBucket[];
  granularity: Granularity;
  onGranularityChange: (g: Granularity) => void;
  isLoading?: boolean;
}

export function MedianPriceTrend({ data, granularity, onGranularityChange, isLoading }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Median Sale Price</CardTitle>
          <PeriodToggle value={granularity} onChange={onGranularityChange} />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[220px] flex items-center justify-center text-muted-foreground text-sm">
            Loading…
          </div>
        ) : data.length === 0 ? (
          <div className="h-[220px] flex items-center justify-center text-muted-foreground text-sm">
            No market sales match these filters.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v: number) => formatCurrency(v)} tick={{ fontSize: 11 }} width={55} />
              <Tooltip
                formatter={(v: number) => [formatCurrency(v), "Median Price"]}
                labelStyle={{ fontSize: 12 }}
              />
              <Line
                type="linear"
                dataKey="median_price"
                stroke="hsl(var(--chart-1))"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
