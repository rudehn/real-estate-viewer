"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils/formatters";
import type { OwnerStats } from "@/lib/types/api";

interface Props {
  buyers: OwnerStats[];
  sellers: OwnerStats[];
}

function OwnerChart({ data, title, color }: { data: OwnerStats[]; title: string; color: string }) {
  const chartData = data.slice(0, 15).map((d) => ({
    name: d.owner_name.length > 22 ? d.owner_name.slice(0, 22) + "…" : d.owner_name,
    count: d.transaction_count,
    total: d.total_spent,
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={360}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 20, top: 4, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-muted" />
            <XAxis type="number" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={150} interval={0} />
            <Tooltip
              formatter={(v: number, n: string) => [
                n === "count" ? `${v} transactions` : formatCurrency(v),
                n === "count" ? "Transactions" : "Total Spent",
              ]}
              labelStyle={{ fontSize: 11 }}
            />
            <Bar dataKey="count" fill={color} radius={[0, 2, 2, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export function TopBuyersSellers({ buyers, sellers }: Props) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <OwnerChart data={buyers} title="Top Buyers" color="hsl(var(--chart-1))" />
      <OwnerChart data={sellers} title="Top Sellers" color="hsl(var(--chart-3))" />
    </div>
  );
}
