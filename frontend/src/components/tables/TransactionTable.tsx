"use client";

import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from "@tanstack/react-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatCurrencyFull, formatDate } from "@/lib/utils/formatters";
import type { TransactionResponse } from "@/lib/types/api";
import Link from "next/link";

const col = createColumnHelper<TransactionResponse>();

const COLUMNS = [
  col.accessor("sale_date", {
    header: "Date",
    cell: (i) => <span className="whitespace-nowrap">{formatDate(i.getValue())}</span>,
  }),
  col.accessor("parcel_location", {
    header: "Address",
    cell: (i) => (
      <Link
        href={`/dashboard/parcels/${i.row.original.parcel_id}`}
        className="text-blue-600 hover:underline max-w-[180px] block truncate"
      >
        {i.getValue()}
      </Link>
    ),
  }),
  col.accessor("sale_price", {
    header: "Sale Price",
    cell: (i) => (
      <span className="font-medium tabular-nums">{formatCurrencyFull(i.getValue())}</span>
    ),
  }),
  col.accessor("parcel_class", {
    header: "Class",
    cell: (i) => <Badge variant="outline" className="text-xs">{i.getValue()}</Badge>,
  }),
  col.accessor("acres", {
    header: "Acres",
    cell: (i) => <span className="tabular-nums">{i.getValue().toFixed(2)}</span>,
  }),
  col.accessor("new_owner", {
    header: "Buyer",
    cell: (i) => <span className="max-w-[140px] block truncate">{i.getValue()}</span>,
  }),
  col.accessor("old_owner", {
    header: "Seller",
    cell: (i) => <span className="max-w-[140px] block truncate">{i.getValue()}</span>,
  }),
  col.accessor("neighborhood", {
    header: "Nbhd",
    cell: (i) => i.getValue() ?? "—",
  }),
];

interface Props {
  data: TransactionResponse[];
  totalCount: number;
}

export function TransactionTable({ data, totalCount }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "sale_date", desc: true }]);

  const table = useReactTable({
    data,
    columns: COLUMNS,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    state: { sorting },
    onSortingChange: setSorting,
    initialState: { pagination: { pageSize: 50 } },
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">
          Transactions ({data.length.toLocaleString()} shown of {totalCount.toLocaleString()} total)
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 border-b">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => (
                    <th
                      key={h.id}
                      className="text-left px-3 py-2 font-medium text-muted-foreground whitespace-nowrap cursor-pointer select-none hover:text-foreground"
                      onClick={h.column.getToggleSortingHandler()}
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b hover:bg-muted/30 transition-colors">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-1.5">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-2 border-t text-xs text-muted-foreground">
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              ← Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              Next →
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
