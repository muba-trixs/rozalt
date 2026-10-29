"use client";

import { useMemo } from "react";
import type { RegionalRow, SeriesPoint } from "@/lib/types";
import { baseAxis, C, EChart, tooltipBase } from "./EChart";

const ms = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`).getTime();

/** Daily forecast error (% variance of recorded sales vs forecast), colored by sign. */
export function ErrorBars({ points, height = 180 }: { points: SeriesPoint[]; height?: number }) {
  const option = useMemo(
    () => ({
      grid: { left: 52, right: 20, top: 12, bottom: 28 },
      xAxis: { type: "time", ...baseAxis, splitLine: { show: false } },
      yAxis: {
        type: "value",
        ...baseAxis,
        axisLine: { show: false },
        axisLabel: { ...baseAxis.axisLabel, formatter: "{value}%" },
      },
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        valueFormatter: (v: number) => `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}%`,
      },
      dataZoom: [{ type: "inside" }],
      series: [
        {
          name: "Variance vs forecast",
          type: "bar",
          barMaxWidth: 4,
          data: points.map((p) => ({
            value: [ms(p.date), p.variance_pct],
            itemStyle: { color: (p.variance_pct ?? 0) < 0 ? C.negative : C.positive, opacity: Math.abs(p.variance_pct ?? 0) >= 12 ? 0.95 : 0.4 },
          })),
          markLine: {
            symbol: "none",
            silent: true,
            data: [{ yAxis: 0 }],
            lineStyle: { color: C.subtle, type: "solid", width: 1 },
            label: { show: false },
          },
        },
      ],
    }),
    [points],
  );
  return <EChart option={option} height={height} />;
}

/** Regional comparison: variance of recorded sales vs forecast per region (diverging around zero). */
export function RegionalBars({ rows, focus, height = 200 }: { rows: RegionalRow[]; focus?: string; height?: number }) {
  const option = useMemo(
    () => ({
      grid: { left: 92, right: 52, top: 8, bottom: 20 },
      xAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: "{value}%" } },
      yAxis: {
        type: "category",
        data: rows.map((r) => r.region),
        ...baseAxis,
        axisLine: { show: false },
        axisLabel: { ...baseAxis.axisLabel, fontFamily: C.sans, fontSize: 11, color: C.muted },
      },
      tooltip: {
        ...tooltipBase,
        trigger: "item",
        formatter: (p: any) => {
          const r = rows[p.dataIndex];
          return `<b>${r.region}</b><br/>Variance ${r.variance_pct?.toFixed(2)}%<br/>MAPE ${r.mape_pct?.toFixed(1)}%<br/>Bias ${r.bias_pct?.toFixed(2)}%<br/>Anomalies ${r.anomaly_count}`;
        },
      },
      series: [
        {
          type: "bar",
          barWidth: 10,
          data: rows.map((r) => ({
            value: Number((r.variance_pct ?? 0).toFixed(2)),
            itemStyle: {
              color: (r.variance_pct ?? 0) < 0 ? C.negative : C.positive,
              opacity: !focus || focus === r.region ? 0.9 : 0.35,
              borderRadius: (r.variance_pct ?? 0) < 0 ? [2, 0, 0, 2] : [0, 2, 2, 0],
            },
          })),
          label: {
            show: true,
            position: "right",
            color: C.muted,
            fontFamily: C.mono,
            fontSize: 10,
            formatter: (p: any) => `${p.value > 0 ? "+" : ""}${p.value.toFixed(2)}%`,
          },
          markLine: { symbol: "none", silent: true, data: [{ xAxis: 0 }], lineStyle: { color: C.subtle }, label: { show: false } },
        },
      ],
    }),
    [rows, focus],
  );
  return <EChart option={option} height={height} />;
}

/** Compact sparkline for KPI tiles / lists. */
export function Sparkline({ values, color = C.cyan, height = 28 }: { values: number[]; color?: string; height?: number }) {
  const option = useMemo(
    () => ({
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: "category", show: false, data: values.map((_, i) => i) },
      yAxis: { type: "value", show: false, scale: true },
      series: [{ type: "line", data: values, showSymbol: false, lineStyle: { color, width: 1.2 }, silent: true }],
    }),
    [values, color],
  );
  return <EChart option={option} height={height} />;
}
