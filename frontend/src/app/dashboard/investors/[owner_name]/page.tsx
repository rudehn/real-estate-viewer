"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { useOwnerHoldings, useOwnerProfile } from "@/lib/hooks/useAnalytics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { HoldingsTable } from "@/components/tables/HoldingsTable";
import { KpiCard } from "@/components/kpi/KpiCard";
import { formatCurrency, formatDate } from "@/lib/utils/formatters";

const HoldingsMap = dynamic(() => import("@/components/map/HoldingsMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-lg" />,
});

function formatHold(days: number): string {
  if (days < 365) return `${Math.round(days / 30)} mo`;
  return `${(days / 365).toFixed(1)} yrs`;
}

export default function InvestorProfilePage() {
  const params = useParams<{ owner_name: string }>();
  const ownerName = decodeURIComponent(params.owner_name);

  const { data: profile, isLoading: profileLoading } = useOwnerProfile(ownerName);
  const { data: holdings = [], isLoading: holdingsLoading } = useOwnerHoldings(ownerName);

  const totalAssessed = holdings.reduce((s, p) => s + (p.assessed_total ?? 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/dashboard/investors" className="text-sm text-muted-foreground hover:text-foreground">
          ← Investors
        </Link>
      </div>

      <div>
        <h1 className="text-xl font-semibold">{ownerName}</h1>
        {profile?.first_activity && (
          <p className="text-sm text-muted-foreground">
            Active {formatDate(profile.first_activity)} – {formatDate(profile.last_activity!)}
          </p>
        )}
      </div>

      {/* Related entities */}
      {profile && profile.related_owners.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Related entities
              <span className="text-muted-foreground font-normal ml-2 text-xs">
                (buy under the same mailing address)
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {profile.related_owners.map((r) => (
              <Link
                key={r.owner_name}
                href={`/dashboard/investors/${encodeURIComponent(r.owner_name)}`}
                title={`Shares ${r.shared_address}`}
              >
                <Badge variant="secondary" className="hover:bg-primary hover:text-primary-foreground transition-colors">
                  {r.owner_name} · {r.transaction_count}
                </Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Current Holdings"
          value={holdings.length.toLocaleString()}
          isLoading={holdingsLoading}
        />
        <KpiCard
          title="Assessed Value Held"
          value={formatCurrency(totalAssessed)}
          isLoading={holdingsLoading}
        />
        <KpiCard
          title="Purchases / Sales"
          value={`${profile?.total_buys ?? 0} / ${profile?.total_sells ?? 0}`}
          isLoading={profileLoading}
        />
        <KpiCard
          title="Median Hold"
          value={profile?.median_hold_days ? formatHold(profile.median_hold_days) : "—"}
          isLoading={profileLoading}
        />
      </div>

      {/* Activity chart + map */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Activity by Year</CardTitle>
          </CardHeader>
          <CardContent>
            {profileLoading ? (
              <Skeleton className="h-[280px]" />
            ) : !profile || profile.activity.length === 0 ? (
              <div className="h-[280px] flex items-center justify-center text-sm text-muted-foreground">
                No recorded activity.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={profile.activity} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} width={40} allowDecimals={false} />
                  <Tooltip labelStyle={{ fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="buy_count" name="Purchases" fill="hsl(var(--chart-1))" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                  <Bar dataKey="sell_count" name="Sales" fill="hsl(var(--chart-3))" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <div className="min-h-[340px]">
          {holdingsLoading ? (
            <Skeleton className="h-full w-full rounded-lg" />
          ) : (
            <HoldingsMap holdings={holdings} />
          )}
        </div>
      </div>

      {/* Holdings table */}
      {holdingsLoading ? (
        <Skeleton className="h-[300px] rounded-lg" />
      ) : (
        <HoldingsTable holdings={holdings} />
      )}
    </div>
  );
}
