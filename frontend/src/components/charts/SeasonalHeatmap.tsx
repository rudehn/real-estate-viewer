"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MarketStatsBucket } from "@/lib/types/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LOW = [219, 234, 254]; // blue-100
const HIGH = [29, 78, 216];   // blue-700

function lerp(a: number[], b: number[], t: number) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t));
}

interface Props {
  /** Monthly market-stats buckets ("YYYY-MM" periods). */
  monthly: MarketStatsBucket[];
}

export function SeasonalHeatmap({ monthly }: Props) {
  if (monthly.length === 0) return null;

  const cellMap = new Map<string, number>();
  const yearSet = new Set<number>();
  for (const b of monthly) {
    const [y, m] = b.period.split("-").map(Number);
    if (!y || !m) continue;
    yearSet.add(y);
    cellMap.set(`${y}-${m}`, b.transaction_count);
  }
  const years = Array.from(yearSet).sort();
  const maxCount = Math.max(...Array.from(cellMap.values()), 1);

  const CELL_W = 18;
  const CELL_H = 14;
  const MONTH_LABEL_W = 28;
  const YEAR_LABEL_H = 20;
  const SVG_W = MONTH_LABEL_W + years.length * CELL_W + 4;
  const SVG_H = YEAR_LABEL_H + 12 * CELL_H + 4;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Seasonal Activity (Market Sales by Month)</CardTitle>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <svg width={SVG_W} height={SVG_H}>
          {/* Month labels */}
          {MONTHS.map((m, mi) => (
            <text
              key={m}
              x={MONTH_LABEL_W - 4}
              y={YEAR_LABEL_H + mi * CELL_H + CELL_H / 2 + 4}
              fontSize={9}
              textAnchor="end"
              fill="currentColor"
              className="fill-muted-foreground"
            >
              {m}
            </text>
          ))}
          {/* Year labels */}
          {years.map((yr, yi) => (
            <text
              key={yr}
              x={MONTH_LABEL_W + yi * CELL_W + CELL_W / 2}
              y={YEAR_LABEL_H - 4}
              fontSize={9}
              textAnchor="middle"
              fill="currentColor"
              className="fill-muted-foreground"
            >
              {yi % 4 === 0 ? yr : ""}
            </text>
          ))}
          {/* Cells */}
          {years.map((yr, yi) =>
            MONTHS.map((_, mi) => {
              const count = cellMap.get(`${yr}-${mi + 1}`) ?? 0;
              const t = count / maxCount;
              const [r, g, b] = lerp(LOW, HIGH, t);
              return (
                <rect
                  key={`${yr}-${mi}`}
                  x={MONTH_LABEL_W + yi * CELL_W + 1}
                  y={YEAR_LABEL_H + mi * CELL_H + 1}
                  width={CELL_W - 2}
                  height={CELL_H - 2}
                  fill={`rgb(${r},${g},${b})`}
                  rx={1}
                >
                  <title>{`${MONTHS[mi]} ${yr}: ${count} market sales`}</title>
                </rect>
              );
            })
          )}
        </svg>
      </CardContent>
    </Card>
  );
}
