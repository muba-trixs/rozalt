"use client";

import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { cn, fmtDate, fmtInt } from "@/lib/format";
import type { Anomaly } from "@/lib/types";
import { InvestigateButton } from "../investigation/InvestigateButton";
import { SeverityBadge, StatusBadge, Variance } from "../ui";

export const anomalyColumns: ColumnDef<Anomaly>[] = [
  {
    id: "anomaly_id",
    header: "ID",
    accessorKey: "anomaly_id",
    cell: (c) => <span className="font-mono text-xs text-subtle">{c.getValue<string>()}</span>,
    size: 84,
  },
  {
    id: "sku_id",
    header: "SKU",
    accessorKey: "sku_id",
    cell: (c) => <span className="font-mono text-xs text-fg">{c.getValue<string>()}</span>,
    size: 84,
  },
  {
    id: "product",
    header: "Product",
    accessorKey: "product_name",
    enableSorting: false,
    cell: (c) => <span className="truncate">{c.getValue<string>()}</span>,
  },
  { id: "region", header: "Region", accessorKey: "region", size: 110 },
  {
    id: "start_date",
    header: "Date",
    accessorKey: "start_date",
    cell: (c) => (
      <span className="font-mono text-xs">
        {fmtDate(c.row.original.start_date)}
        <span className="text-subtle"> · {c.row.original.duration_days}d</span>
      </span>
    ),
    size: 128,
  },
  {
    id: "forecast",
    header: "Forecast",
    accessorKey: "forecast_qty",
    enableSorting: false,
    cell: (c) => <span className="font-mono text-xs num">{fmtInt(c.getValue<number>())}</span>,
    meta: { align: "right" },
    size: 90,
  },
  {
    id: "recorded",
    header: "Recorded",
    accessorKey: "recorded_sales_qty",
    enableSorting: false,
    cell: (c) => <span className="font-mono text-xs num">{fmtInt(c.getValue<number>())}</span>,
    meta: { align: "right" },
    size: 90,
  },
  {
    id: "abs_variance",
    header: "Forecast Var.",
    accessorKey: "variance_pct",
    cell: (c) => <Variance value={c.getValue<number>()} className="text-xs" />,
    meta: { align: "right" },
    size: 100,
  },
  {
    id: "severity",
    header: "Severity",
    accessorKey: "severity",
    cell: (c) => <SeverityBadge severity={c.row.original.severity} />,
    size: 92,
  },
  {
    id: "status",
    header: "Investigation",
    accessorKey: "status",
    cell: (c) => <StatusBadge status={c.row.original.latest_investigation_status ?? (c.row.original.status === "NEW" ? null : c.row.original.status)} />,
    size: 130,
  },
  {
    id: "action",
    header: "",
    enableSorting: false,
    cell: (c) => (
      <InvestigateButton anomalyId={c.row.original.anomaly_id} investigationId={c.row.original.latest_investigation_id} />
    ),
    size: 104,
  },
];

export function AnomalyTable({
  rows,
  sorting,
  onSortingChange,
  focusId,
  manualSorting = true,
  hiddenColumns = [],
}: {
  rows: Anomaly[];
  sorting?: SortingState;
  onSortingChange?: (s: SortingState) => void;
  focusId?: string | null;
  manualSorting?: boolean;
  hiddenColumns?: string[];
}) {
  const table = useReactTable({
    data: rows,
    columns: anomalyColumns.filter((c) => !hiddenColumns.includes(c.id!)),
    state: { sorting: sorting ?? [] },
    manualSorting,
    enableSortingRemoval: false,
    onSortingChange: (u) => {
      const next = typeof u === "function" ? u(sorting ?? []) : u;
      onSortingChange?.(next);
    },
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <table className="table-dense w-full table-fixed">
      <thead>
        {table.getHeaderGroups().map((hg) => (
          <tr key={hg.id}>
            {hg.headers.map((h) => {
              const can = h.column.getCanSort() && !!onSortingChange;
              const dir = h.column.getIsSorted();
              const align = (h.column.columnDef.meta as { align?: string } | undefined)?.align;
              return (
                <th
                  key={h.id}
                  style={{ width: h.column.columnDef.size }}
                  className={cn(can && "cursor-pointer select-none hover:text-fg", align === "right" && "text-right")}
                  onClick={can ? h.column.getToggleSortingHandler() : undefined}
                >
                  <span className={cn("inline-flex items-center gap-1", align === "right" && "flex-row-reverse")}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {can &&
                      (dir === "asc" ? (
                        <ArrowUp className="h-3 w-3 text-accent" />
                      ) : dir === "desc" ? (
                        <ArrowDown className="h-3 w-3 text-accent" />
                      ) : (
                        <ArrowUpDown className="h-3 w-3 opacity-30" />
                      ))}
                  </span>
                </th>
              );
            })}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((r) => (
          <tr key={r.id} className={cn(focusId === r.original.anomaly_id && "!bg-accent/10")} id={`row-${r.original.anomaly_id}`}>
            {r.getVisibleCells().map((c) => {
              const align = (c.column.columnDef.meta as { align?: string } | undefined)?.align;
              return (
                <td key={c.id} className={cn("truncate", align === "right" && "text-right")}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
