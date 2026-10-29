"use client";

import { useMemo } from "react";
import { addDays, fmtInt, titleCase } from "@/lib/format";
import type { Anomaly, SeriesPoint } from "@/lib/types";
import { baseAxis, C, EChart, tooltipBase } from "./EChart";

export interface TimelineEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  lane: string; // e.g. driver type
  emphasis?: "candidate" | "screened";
  score?: number;
}

interface Props {
  points: SeriesPoint[];
  anomalies?: Pick<Anomaly, "anomaly_id" | "start_date" | "end_date" | "direction">[];
  investigationWindow?: { start: string; end: string } | null;
  events?: TimelineEvent[];
  highlightEventId?: string | null;
  onEventClick?: (id: string) => void;
  onAnomalyClick?: (id: string) => void;
  showBaseline?: boolean;
  showEstimate?: boolean;
  zoomRange?: { start: string; end: string } | null;
  height?: number;
}

const LANE_LABEL: Record<string, string> = {
  distribution_disruption: "DISTRIBUTION",
  internal_promotion: "PROMOTION",
  competitor_activity: "COMPETITOR",
  product_quality: "QUALITY",
  cultural_event: "CULTURAL",
  operational_routine: "ROUTINE OPS",
  inventory_constraint: "INVENTORY",
  macroeconomic: "MACRO",
};

const ms = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`).getTime();

/**
 * Forecast (dashed blue) vs recorded sales (solid cyan), seasonal baseline (muted dotted) and —
 * on stockout days only — estimated unconstrained demand (amber points, flagged as an estimate).
 * Optional second grid: event timeline sharing the time axis and zoom with the demand chart.
 */
export function DemandChart({
  points,
  anomalies = [],
  investigationWindow,
  events = [],
  highlightEventId,
  onEventClick,
  onAnomalyClick,
  showBaseline = true,
  showEstimate = true,
  zoomRange,
  height = 340,
}: Props) {
  const option = useMemo(() => {
    const hasTimeline = events.length > 0;
    const lanes = Array.from(new Set(events.map((e) => e.lane)));
    const laneH = 18;
    const timelineH = hasTimeline ? Math.max(lanes.length, 1) * laneH + 8 : 0;
    const mainBottom = hasTimeline ? timelineH + 72 : 52;

    const forecast = points.map((p) => [ms(p.date), p.forecast_qty]);
    const sales = points.map((p) => [ms(p.date), p.recorded_sales_qty]);
    const baseline = points.map((p) => [ms(p.date), p.seasonal_baseline]);
    const estimate = points
      .filter((p) => p.estimated_unconstrained_demand != null)
      .map((p) => [ms(p.date), p.estimated_unconstrained_demand]);

    const markAreas: any[] = anomalies.map((a) => {
      const neg = a.direction === "NEGATIVE";
      return [
        {
          name: a.anomaly_id,
          xAxis: ms(a.start_date),
          itemStyle: { color: neg ? "rgba(248,81,73,0.09)" : "rgba(63,185,80,0.09)", borderColor: neg ? "rgba(248,81,73,.45)" : "rgba(63,185,80,.45)", borderWidth: 1, borderType: "dashed" },
          label: { show: !investigationWindow, color: neg ? C.negative : C.positive, fontFamily: C.mono, fontSize: 9, position: "insideTop" },
        },
        { xAxis: ms(addDays(a.end_date, 1)) },
      ];
    });
    if (investigationWindow) {
      markAreas.push([
        {
          name: "INVESTIGATION WINDOW",
          xAxis: ms(investigationWindow.start),
          itemStyle: { color: "rgba(88,166,255,0.06)" },
          label: { color: C.blue, fontFamily: C.mono, fontSize: 9, position: "insideTopLeft", offset: [4, 4] },
        },
        { xAxis: ms(addDays(investigationWindow.end, 1)) },
      ]);
    }
    const hl = events.find((e) => e.id === highlightEventId);
    if (hl) {
      markAreas.push([
        {
          name: hl.id,
          xAxis: ms(hl.start),
          itemStyle: { color: "rgba(210,153,34,0.14)", borderColor: "rgba(210,153,34,.7)", borderWidth: 1 },
          label: { color: C.warning, fontFamily: C.mono, fontSize: 9, position: "insideBottom" },
        },
        { xAxis: ms(addDays(hl.end, 1)) },
      ]);
    }
    const markLines = events
      .filter((e) => e.emphasis === "candidate")
      .map((e) => ({
        xAxis: ms(e.start),
        lineStyle: { color: e.id === highlightEventId ? C.warning : "rgba(139,148,158,.55)", type: "dashed", width: 1 },
        label: { show: true, formatter: e.id, color: e.id === highlightEventId ? C.warning : C.subtle, fontFamily: C.mono, fontSize: 9, position: "end" },
      }));

    // Both grids share an identical time extent so the event timeline stays aligned under zoom.
    const xMin = points.length ? ms(points[0].date) : undefined;
    const xMax = points.length ? ms(points[points.length - 1].date) : undefined;
    const left = hasTimeline ? 96 : 64;
    const grids: any[] = [{ left, right: 20, top: 34, bottom: mainBottom }];
    const xAxes: any[] = [
      { type: "time", gridIndex: 0, min: xMin, max: xMax, ...baseAxis, splitLine: { show: false }, axisLabel: { ...baseAxis.axisLabel, hideOverlap: true } },
    ];
    const yAxes: any[] = [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        ...baseAxis,
        axisLine: { show: false },
        axisLabel: { ...baseAxis.axisLabel, formatter: (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}K` : `${v}`) },
      },
    ];
    if (hasTimeline) {
      grids.push({ left, right: 20, height: timelineH, bottom: 44 });
      xAxes.push({ type: "time", gridIndex: 1, min: xMin, max: xMax, ...baseAxis, axisLabel: { show: false }, splitLine: { show: false }, axisLine: { lineStyle: { color: C.border } } });
      yAxes.push({
        type: "category",
        gridIndex: 1,
        data: lanes,
        inverse: true,
        ...baseAxis,
        axisLine: { show: false },
        splitLine: { show: true, lineStyle: { color: "rgba(48,54,61,.35)" } },
        axisLabel: { ...baseAxis.axisLabel, fontSize: 9, formatter: (v: string) => LANE_LABEL[v] ?? titleCase(v).toUpperCase().slice(0, 14) },
      });
    }

    const series: any[] = [
      {
        name: "Forecast",
        type: "line",
        data: forecast,
        showSymbol: false,
        lineStyle: { color: C.blue, width: 1.5, type: [5, 3] },
        itemStyle: { color: C.blue },
        z: 3,
        markLine: markLines.length ? { symbol: "none", silent: true, data: markLines, animation: false } : undefined,
      },
      {
        name: "Recorded sales",
        type: "line",
        data: sales,
        showSymbol: false,
        lineStyle: { color: C.cyan, width: 1.6 },
        itemStyle: { color: C.cyan },
        z: 4,
        markArea: markAreas.length ? { silent: !onAnomalyClick, data: markAreas } : undefined,
      },
    ];
    if (showBaseline)
      series.push({
        name: "Seasonal baseline",
        type: "line",
        data: baseline,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { color: C.subtle, width: 1, type: "dotted" },
        itemStyle: { color: C.subtle },
        z: 2,
      });
    if (showEstimate && estimate.length)
      series.push({
        name: "Est. unconstrained demand",
        type: "scatter",
        data: estimate,
        symbol: "diamond",
        symbolSize: 8,
        itemStyle: { color: C.warning, borderColor: C.bg, borderWidth: 1.5 },
        z: 5,
      });
    if (hasTimeline) {
      const laneIdx = new Map(lanes.map((l, i) => [l, i]));
      series.push({
        name: "Events",
        type: "custom",
        xAxisIndex: 1,
        yAxisIndex: 1,
        encode: { x: [0, 1], y: 2 },
        data: events.map((e) => ({
          value: [ms(e.start), ms(addDays(e.end, 1)), laneIdx.get(e.lane), e.id],
          event: e,
        })),
        renderItem: (params: any, api: any) => {
          const lane = api.value(2);
          const s = api.coord([api.value(0), lane]);
          const en = api.coord([api.value(1), lane]);
          const h = laneH - 7;
          const ev: TimelineEvent = events[params.dataIndex];
          const isHl = ev.id === highlightEventId;
          const color = isHl ? C.warning : ev.emphasis === "candidate" ? C.blue : C.subtle;
          const w = Math.max(en[0] - s[0], 4);
          return {
            type: "group",
            children: [
              {
                type: "rect",
                shape: { x: s[0], y: s[1] - h / 2, width: w, height: h, r: 2 },
                style: { fill: color, opacity: isHl ? 0.95 : ev.emphasis === "candidate" ? 0.7 : 0.35, stroke: isHl ? "#fff" : undefined, lineWidth: isHl ? 1 : 0 },
              },
              w > 46
                ? {
                    type: "text",
                    style: { x: s[0] + 4, y: s[1], text: ev.id, fill: C.bg, font: `600 9px ${C.mono}`, verticalAlign: "middle" },
                    silent: true,
                  }
                : null,
            ].filter(Boolean),
          };
        },
        z: 6,
      });
    }

    const startZoom = zoomRange ? ms(zoomRange.start) : undefined;
    const endZoom = zoomRange ? ms(zoomRange.end) : undefined;

    return {
      backgroundColor: "transparent",
      textStyle: { fontFamily: C.sans },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      legend: {
        top: 4,
        left: left - 4,
        itemWidth: 16,
        itemHeight: 8,
        icon: "roundRect",
        textStyle: { color: C.muted, fontSize: 11 },
        data: series.filter((s) => s.name !== "Events").map((s) => s.name),
      },
      axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: C.subtle, width: 1, type: "solid" } },
      tooltip: {
        ...tooltipBase,
        trigger: "axis",
        axisPointer: { type: "cross", label: { backgroundColor: C.elevated, color: C.text, fontFamily: C.mono, fontSize: 10, borderColor: C.border, borderWidth: 1 } },
        formatter: (ps: any[]) => {
          if (!ps?.length) return "";
          const date = new Date(ps[0].axisValue).toISOString().slice(0, 10);
          const p = points.find((x) => x.date === date);
          if (!p) {
            const ev = ps.find((x) => x.seriesName === "Events")?.data?.event as TimelineEvent | undefined;
            return ev ? `<b>${ev.id}</b><br/>${ev.title}` : date;
          }
          const row = (dot: string, label: string, v: string, dashed = false) =>
            `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${C.muted}"><span style="display:inline-block;width:10px;height:0;border-top:2px ${dashed ? "dashed" : "solid"} ${dot};margin-right:6px;vertical-align:middle"></span>${label}</span><span>${v}</span></div>`;
          const v = p.variance_pct;
          const vColor = v == null ? C.muted : v < 0 ? C.negative : C.positive;
          let html = `<div style="min-width:220px"><div style="color:${C.muted};margin-bottom:4px">${date}</div>`;
          html += row(C.blue, "Forecast", fmtInt(p.forecast_qty), true);
          html += row(C.cyan, "Recorded sales", fmtInt(p.recorded_sales_qty));
          if (showBaseline && p.seasonal_baseline != null) html += row(C.subtle, "Seasonal baseline", fmtInt(p.seasonal_baseline), true);
          html += `<div style="display:flex;justify-content:space-between;gap:16px;margin-top:3px;border-top:1px solid ${C.border};padding-top:3px"><span style="color:${C.muted}">Variance vs forecast</span><span style="color:${vColor}">${v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}</span></div>`;
          if (p.available_inventory != null) html += row(C.border, "Available inventory", fmtInt(p.available_inventory));
          if (p.stockout_flag) html += `<div style="color:${C.warning};margin-top:3px">■ STOCKOUT — recorded sales bounded by availability</div>`;
          if (p.estimated_unconstrained_demand != null)
            html += row(C.warning, "Est. demand (estimate)", fmtInt(p.estimated_unconstrained_demand));
          return html + "</div>";
        },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: hasTimeline ? [0, 1] : [0], startValue: startZoom, endValue: endZoom },
        {
          type: "slider",
          xAxisIndex: hasTimeline ? [0, 1] : [0],
          height: 18,
          bottom: 10,
          startValue: startZoom,
          endValue: endZoom,
          borderColor: C.border,
          backgroundColor: "transparent",
          fillerColor: "rgba(88,166,255,0.10)",
          dataBackground: { lineStyle: { color: C.subtle, width: 0.8 }, areaStyle: { color: "rgba(110,118,129,.15)" } },
          selectedDataBackground: { lineStyle: { color: C.cyan, width: 0.8 }, areaStyle: { color: "rgba(57,197,207,.12)" } },
          handleStyle: { color: C.elevated, borderColor: C.subtle },
          moveHandleStyle: { color: C.border },
          textStyle: { color: C.subtle, fontFamily: C.mono, fontSize: 9 },
          brushSelect: false,
        },
      ],
      series,
    };
  }, [points, anomalies, investigationWindow, events, highlightEventId, showBaseline, showEstimate, zoomRange, onAnomalyClick]);

  const onEvents = useMemo(
    () => ({
      click: (p: any) => {
        if (p.seriesType === "custom" && p.data?.event) onEventClick?.(p.data.event.id);
        else if (p.componentType === "markArea" && p.name?.startsWith("ANM-")) onAnomalyClick?.(p.name);
      },
    }),
    [onEventClick, onAnomalyClick],
  );

  const totalH = height + (events.length ? Array.from(new Set(events.map((e) => e.lane))).length * 18 + 30 : 0);
  return <EChart option={option} height={totalH} onEvents={onEvents} />;
}
