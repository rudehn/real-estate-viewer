"use client";

import { useFilters } from "@/lib/hooks/useFilters";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/utils/formatters";
import type { ParcelClass } from "@/lib/types/api";

const CLASS_COLORS: Record<ParcelClass, string> = {
  Residential: "bg-blue-500",
  Commercial: "bg-orange-500",
  Industrial: "bg-purple-500",
  Agricultural: "bg-green-500",
  Exempt: "bg-gray-400",
  Utilities: "bg-yellow-500",
};

export function FilterSidebar() {
  const { rawFilters, setFilters, resetFilters, PARCEL_CLASSES } = useFilters();

  return (
    <aside className="w-64 min-h-screen border-r bg-muted/20 p-4 flex flex-col gap-5 shrink-0">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-sm">Filters</h2>
        <Button variant="ghost" size="sm" onClick={resetFilters} className="text-xs h-7">
          Reset
        </Button>
      </div>

      {/* Date Range */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Date Range
        </label>
        <div className="mt-2 flex flex-col gap-2">
          <div>
            <span className="text-xs text-muted-foreground">From</span>
            <input
              type="date"
              value={rawFilters.sale_date__gte}
              onChange={(e) => void setFilters({ sale_date__gte: e.target.value })}
              className="w-full mt-1 text-sm border rounded px-2 py-1 bg-background"
            />
          </div>
          <div>
            <span className="text-xs text-muted-foreground">To</span>
            <input
              type="date"
              value={rawFilters.sale_date__lte}
              onChange={(e) => void setFilters({ sale_date__lte: e.target.value })}
              className="w-full mt-1 text-sm border rounded px-2 py-1 bg-background"
            />
          </div>
        </div>
      </div>

      {/* Price Range */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Price Range
        </label>
        <div className="mt-3 px-1">
          <Slider
            min={0}
            max={2_000_000}
            step={10_000}
            value={[rawFilters.sale_price__gte, Math.min(rawFilters.sale_price__lte, 2_000_000)]}
            onValueChange={(val) => {
              const vals = val as number[];
              void setFilters({ sale_price__gte: vals[0], sale_price__lte: vals[1] });
            }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground mt-1">
          <span>{formatCurrency(rawFilters.sale_price__gte)}</span>
          <span>
            {rawFilters.sale_price__lte >= 2_000_000
              ? "2M+"
              : formatCurrency(rawFilters.sale_price__lte)}
          </span>
        </div>
      </div>

      {/* Acres Range */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Acreage
        </label>
        <div className="mt-3 px-1">
          <Slider
            min={0}
            max={100}
            step={0.5}
            value={[rawFilters.acres__gte, Math.min(rawFilters.acres__lte, 100)]}
            onValueChange={(val) => {
              const vals = val as number[];
              void setFilters({ acres__gte: vals[0], acres__lte: vals[1] });
            }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground mt-1">
          <span>{rawFilters.acres__gte.toFixed(1)} ac</span>
          <span>
            {rawFilters.acres__lte >= 100 ? "100+ ac" : `${rawFilters.acres__lte.toFixed(0)} ac`}
          </span>
        </div>
      </div>

      {/* Property Class */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Property Class
        </label>
        <div className="mt-2 flex flex-col gap-2">
          {PARCEL_CLASSES.map((cls) => {
            const checked = rawFilters.parcel_class__in.includes(cls);
            return (
              <label key={cls} className="flex items-center gap-2 cursor-pointer">
                <Checkbox
                  checked={checked}
                  onCheckedChange={(val) => {
                    const next = val
                      ? [...rawFilters.parcel_class__in, cls]
                      : rawFilters.parcel_class__in.filter((c) => c !== cls);
                    void setFilters({ parcel_class__in: next });
                  }}
                />
                <span className={`w-2 h-2 rounded-full ${CLASS_COLORS[cls]}`} />
                <span className="text-sm">{cls}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Owner Search */}
      <div>
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Owner Search
        </label>
        <input
          type="text"
          placeholder="e.g. SMITH"
          value={rawFilters.new_owner__ilike ?? ""}
          onChange={(e) =>
            void setFilters({ new_owner__ilike: e.target.value || null })
          }
          className="w-full mt-2 text-sm border rounded px-2 py-1.5 bg-background"
        />
      </div>
    </aside>
  );
}
