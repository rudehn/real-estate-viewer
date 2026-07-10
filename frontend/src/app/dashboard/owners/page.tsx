"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useOwnerSearch, useOwnerHoldings } from "@/lib/hooks/useAnalytics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { OwnerParcel } from "@/lib/types/api";

function useDebounce(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

function HoldingsSummary({ parcels }: { parcels: OwnerParcel[] }) {
  const totalAcres = parcels.reduce((s, p) => s + p.acres, 0);
  const totalValue = parcels.reduce((s, p) => s + (p.assessed_total ?? 0), 0);
  return (
    <div className="grid grid-cols-3 gap-3 text-sm">
      <div className="bg-muted/50 rounded-lg p-3">
        <div className="text-muted-foreground text-xs uppercase tracking-wide mb-1">Parcels</div>
        <div className="font-semibold text-lg">{parcels.length}</div>
      </div>
      <div className="bg-muted/50 rounded-lg p-3">
        <div className="text-muted-foreground text-xs uppercase tracking-wide mb-1">Total Acres</div>
        <div className="font-semibold text-lg">{totalAcres.toFixed(2)}</div>
      </div>
      <div className="bg-muted/50 rounded-lg p-3">
        <div className="text-muted-foreground text-xs uppercase tracking-wide mb-1">Assessed Value</div>
        <div className="font-semibold text-lg">{formatCurrencyFull(totalValue)}</div>
      </div>
    </div>
  );
}

export default function OwnersPage() {
  const [input, setInput] = useState("");
  const [selectedOwner, setSelectedOwner] = useState<string | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const debouncedQuery = useDebounce(input, 300);
  const { data: suggestions = [] } = useOwnerSearch(debouncedQuery);
  const { data: holdings = [], isLoading: holdingsLoading } = useOwnerHoldings(selectedOwner);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function selectOwner(name: string) {
    setInput(name);
    setSelectedOwner(name);
    setShowDropdown(false);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    setInput(e.target.value);
    setSelectedOwner(null);
    setShowDropdown(true);
  }

  return (
    <div className="space-y-5 max-w-4xl">
      <h1 className="text-xl font-semibold">Owner Search</h1>

      {/* Search box */}
      <div className="relative" ref={dropdownRef}>
        <input
          type="text"
          value={input}
          onChange={handleInputChange}
          onFocus={() => setShowDropdown(true)}
          placeholder="Search owner name..."
          className="w-full border rounded-lg px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        />
        {showDropdown && suggestions.length > 0 && (
          <div className="absolute z-10 w-full mt-1 bg-background border rounded-lg shadow-lg overflow-hidden">
            {suggestions.map((name) => (
              <button
                key={name}
                onMouseDown={() => selectOwner(name)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-muted truncate"
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results */}
      {selectedOwner && (
        <>
          <div>
            <h2 className="text-base font-medium mb-3">{selectedOwner}</h2>
            {holdingsLoading ? (
              <Skeleton className="h-20 rounded-lg" />
            ) : (
              <HoldingsSummary parcels={holdings} />
            )}
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Current Holdings</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {holdingsLoading ? (
                <div className="p-4"><Skeleton className="h-40" /></div>
              ) : holdings.length === 0 ? (
                <p className="text-sm text-muted-foreground p-4">No current holdings found.</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-muted/50 border-b">
                    <tr>
                      {["Address", "Class", "Acres", "Last Sale", "Last Price", "Assessed"].map((h) => (
                        <th key={h} className="text-left px-3 py-2 font-medium text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {holdings.map((p) => (
                      <tr key={p.parcel_id} className="border-b hover:bg-muted/30">
                        <td className="px-3 py-1.5">
                          <Link
                            href={`/dashboard/parcels/${encodeURIComponent(p.parcel_id)}`}
                            className="text-primary hover:underline"
                          >
                            {p.parcel_location}
                          </Link>
                        </td>
                        <td className="px-3 py-1.5">
                          <Badge variant="outline" className="text-xs">{p.parcel_class}</Badge>
                        </td>
                        <td className="px-3 py-1.5 tabular-nums">{p.acres.toFixed(2)}</td>
                        <td className="px-3 py-1.5 whitespace-nowrap">{formatDate(p.last_sale_date)}</td>
                        <td className="px-3 py-1.5 tabular-nums">{formatCurrencyFull(p.last_sale_price)}</td>
                        <td className="px-3 py-1.5 tabular-nums">
                          {p.assessed_total ? formatCurrencyFull(p.assessed_total) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {!selectedOwner && input.length < 2 && (
        <p className="text-sm text-muted-foreground">Type at least 2 characters to search for an owner.</p>
      )}
    </div>
  );
}
