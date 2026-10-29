"use client";

import { BarChart, CustomChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { useEffect, useRef } from "react";

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  CanvasRenderer,
]);

export const C = {
  bg: "#0D1117",
  surface: "#161B22",
  elevated: "#21262D",
  border: "#30363D",
  grid: "rgba(48,54,61,0.55)",
  text: "#E6EDF3",
  muted: "#8B949E",
  subtle: "#6E7681",
  blue: "#58A6FF",
  cyan: "#39C5CF",
  positive: "#3FB950",
  negative: "#F85149",
  warning: "#D29922",
  mono: "'JetBrains Mono', ui-monospace, monospace",
  sans: "'Inter Variable', Inter, system-ui, sans-serif",
};

export const baseAxis = {
  axisLine: { lineStyle: { color: C.border } },
  axisTick: { show: false },
  axisLabel: { color: C.subtle, fontFamily: C.mono, fontSize: 10 },
  splitLine: { lineStyle: { color: C.grid, width: 1 } },
};

export const tooltipBase = {
  backgroundColor: C.elevated,
  borderColor: C.border,
  borderWidth: 1,
  padding: [6, 8],
  textStyle: { color: C.text, fontFamily: C.mono, fontSize: 11 },
  extraCssText: "border-radius:4px;box-shadow:0 8px 24px rgba(0,0,0,.45);",
};

export function EChart({
  option,
  height = 320,
  onEvents,
  className,
}: {
  option: EChartsCoreOption;
  height?: number | string;
  onEvents?: Record<string, (params: any) => void>;
  className?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const handlers = useRef(onEvents);
  handlers.current = onEvents;

  useEffect(() => {
    if (!el.current) return;
    const inst = echarts.init(el.current, undefined, { renderer: "canvas" });
    chart.current = inst;
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      inst.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const inst = chart.current;
    if (!inst) return;
    inst.setOption({ animation: false, ...option }, { notMerge: true, lazyUpdate: true });
  }, [option]);

  useEffect(() => {
    const inst = chart.current;
    if (!inst || !onEvents) return;
    const names = Object.keys(onEvents);
    names.forEach((n) => inst.on(n, (p: unknown) => handlers.current?.[n]?.(p)));
    return () => names.forEach((n) => inst.off(n));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onEvents ? Object.keys(onEvents).join(",") : ""]);

  return <div ref={el} className={className} style={{ height, width: "100%" }} />;
}
