"use client";

import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PeriodToggle } from "./PeriodToggle";
import { groupByPeriod, type Period } from "@/lib/utils/chartHelpers";
import { formatCurrency } from "@/lib/utils/formatters";
import type { TransactionResponse } from "@/lib/types/api";

interface Props {
  transactions: TransactionResponse[];
  isLoading?: boolean;
}

export function MedianPriceTrend({ transactions, isLoading }: Props) {
  const [period, setPeriod] = useState<Period>("annual");
  const data = groupByPeriod(transactions, period);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Median Sale Price</CardTitle>
          <PeriodToggle value={period} onChange={setPeriod} />
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">
            Loading…
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
              <Line type="monotone" dataKey="median" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
