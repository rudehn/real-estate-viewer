"use client";

import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PeriodToggle } from "./PeriodToggle";
import { groupByPeriod, type Period } from "@/lib/utils/chartHelpers";
import type { TransactionResponse } from "@/lib/types/api";

interface Props {
  transactions: TransactionResponse[];
  isLoading?: boolean;
}

export function TransactionVolume({ transactions, isLoading }: Props) {
  const [period, setPeriod] = useState<Period>("annual");
  const data = groupByPeriod(transactions, period);

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">Transaction Volume</CardTitle>
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
            <BarChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11 }} width={45} />
              <Tooltip labelStyle={{ fontSize: 12 }} />
              <Bar dataKey="count" name="Transactions" fill="hsl(var(--chart-2))" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
