"use client";

import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatDate } from "@/lib/utils/formatters";
import type { TransactionResponse } from "@/lib/types/api";

interface Props {
  transactions: TransactionResponse[];
}

const CLASS_COLORS: Record<string, string> = {
  Residential: "#3b82f6",
  Commercial: "#f97316",
  Industrial: "#8b5cf6",
  Agricultural: "#22c55e",
  Exempt: "#9ca3af",
  Utilities: "#eab308",
};

export function PriceScatter({ transactions }: Props) {
  const data = transactions.map((t) => ({
    x: new Date(t.sale_date + "T00:00:00").getTime(),
    y: t.sale_price,
    label: t.parcel_location,
    date: t.sale_date,
    cls: t.parcel_class,
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Sale Price Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={260}>
          <ScatterChart margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="x"
              type="number"
              domain={["auto", "auto"]}
              tickFormatter={(v) => new Date(v).getFullYear().toString()}
              tick={{ fontSize: 11 }}
              name="Date"
            />
            <YAxis
              dataKey="y"
              tickFormatter={(v) => formatCurrency(v)}
              tick={{ fontSize: 11 }}
              width={60}
              name="Price"
            />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const d = payload[0].payload;
                return (
                  <div className="bg-background border rounded p-2 text-xs shadow">
                    <div className="font-medium">{d.label}</div>
                    <div>{formatDate(d.date)}</div>
                    <div>{formatCurrency(d.y)}</div>
                    <div className="text-muted-foreground">{d.cls}</div>
                  </div>
                );
              }}
            />
            <Scatter
              data={data}
              fill="#3b82f6"
              opacity={0.6}
              shape={(props: unknown) => {
                const { cx, cy, payload } = props as { cx: number; cy: number; payload: { cls: string } };
                return (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={3}
                    fill={CLASS_COLORS[payload.cls] ?? "#3b82f6"}
                    opacity={0.6}
                  />
                );
              }}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
