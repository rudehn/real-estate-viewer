"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PeriodToggle } from "./PeriodToggle";
import type { Granularity, MarketStatsBucket } from "@/lib/types/api";

interface Props {
  data: MarketStatsBucket[];
  granularity: Granularity;
  onGranularityChange: (g: Granularity) => void;
  isLoading?: boolean;
}

export function TransactionVolume({ data, granularity, onGranularityChange, isLoading }: Props) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Market Sales</CardTitle>
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
            <BarChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11 }} width={45} />
              <Tooltip labelStyle={{ fontSize: 12 }} />
              <Bar
                dataKey="transaction_count"
                name="Market sales"
                fill="hsl(var(--chart-2))"
                radius={[2, 2, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
