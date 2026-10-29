"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo } from "react";
import { DemandChart } from "@/components/charts/DemandChart";
import { ErrorBars, RegionalBars } from "@/components/charts/SmallCharts";
import { AnomalyTable } from "@/components/tables/AnomalyTable";
import { IntelPanel } from "@/components/shell/AppShell";
import { EmptyState, ErrorState, KV, Panel, Segmented, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtInt, fmtPct } from "@/lib/format";
import { usePersistentState } from "@/lib/hooks";

interface Prefs {
  sku: string;
  region: string;
  start: string;
  end: string;
  baseline: boolean;
  overlay: "on" | "off";
}

function Analytics() {
  const params = useSearchParams();
  const router = useRouter();
  const [prefs, setPrefs] = usePersistentState<Prefs>("di.analytics", {
    sku: "",
    region: "",
    start: "",
    end: "",
    baseline: true,
    overlay: "on",
  });
  const skus = useQuery({ queryKey: ["skus"], queryFn: api.skus });

  // URL ?sku= wins (command palette deep links); otherwise fall back to persisted / first SKU
  useEffect(() => {
    const fromUrl = params.get("sku");
    if (fromUrl && fromUrl !== prefs.sku) setPrefs((p) => ({ ...p, sku: fromUrl }));
    else if (!prefs.sku && skus.data?.length) setPrefs((p) => ({ ...p, sku: skus.data![0].sku_id }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, skus.data]);

  const sku = skus.data?.find((s) => s.sku_id === prefs.sku);
  const region = sku?.regions.includes(prefs.region) ? prefs.region : sku?.regions[0] ?? "";

  const ts = useQuery({
    queryKey: ["timeseries", prefs.sku, region, prefs.start, prefs.end],
    queryFn: () => api.timeseries(prefs.sku, region, prefs.start || undefined, prefs.end || undefined),
    enabled: !!prefs.sku && !!region,
  });
  const regional = useQuery({
    queryKey: ["regional", prefs.sku, prefs.start, prefs.end],
    queryFn: () => api.regional(prefs.sku, prefs.start || undefined, prefs.end || undefined),
    enabled: !!prefs.sku,
  });

  const stockoutDays = useMemo(() => ts.data?.points.filter((p) => p.stockout_flag).length ?? 0, [ts.data]);
  const s = ts.data?.summary;

  const setSku = (v: string) => {
    setPrefs((p) => ({ ...p, sku: v }));
    router.replace(`/analytics?sku=${v}`);
  };

  return (
    <div className="space-y-3 p-4">
      <div>
        <h1 className="text-lg font-semibold">Demand Analytics</h1>
        <p className="text-sm text-muted">
          Forecast (planned) vs recorded sales (observed, bounded by inventory). Underlying demand is not observed.
        </p>
      </div>

      <div className="panel flex flex-wrap items-center gap-2 px-3 py-2">
        <span className="label">SKU</span>
        <Select value={prefs.sku} onChange={(e) => setSku(e.target.value)} className="w-60">
          {(skus.data ?? []).map((x) => (
            <option key={x.sku_id} value={x.sku_id}>
              {x.sku_id} · {x.product_name}
            </option>
          ))}
        </Select>
        <span className="label ml-2">Region</span>
        <Select value={region} onChange={(e) => setPrefs((p) => ({ ...p, region: e.target.value }))} className="w-40">
          {(sku?.regions ?? []).map((r) => (
            <option key={r}>{r}</option>
          ))}
        </Select>
        <span className="label ml-2">Range</span>
        <input type="date" className="input w-36 shrink-0 font-mono" value={prefs.start} onChange={(e) => setPrefs((p) => ({ ...p, start: e.target.value }))} />
        <span className="text-subtle">→</span>
        <input type="date" className="input w-36 shrink-0 font-mono" value={prefs.end} onChange={(e) => setPrefs((p) => ({ ...p, end: e.target.value }))} />
        <div className="ml-auto flex items-center gap-2">
          <span className="label">Anomaly overlay</span>
          <Segmented
            value={prefs.overlay}
            onChange={(v) => setPrefs((p) => ({ ...p, overlay: v }))}
            options={[
              { value: "on", label: "On" },
              { value: "off", label: "Off" },
            ]}
          />
          <span className="label ml-2">Baseline</span>
          <Segmented
            value={prefs.baseline ? "on" : "off"}
            onChange={(v) => setPrefs((p) => ({ ...p, baseline: v === "on" }))}
            options={[
              { value: "on", label: "On" },
              { value: "off", label: "Off" },
            ]}
          />
        </div>
      </div>

      <Panel title={ts.data ? `${ts.data.sku_id} · ${ts.data.product_name} · ${ts.data.region}` : "Forecast vs recorded sales"}>
        {ts.isError ? (
          <ErrorState error={ts.error} retry={() => ts.refetch()} />
        ) : ts.isLoading || !ts.data ? (
          <Skeleton className="m-3 h-[340px] w-auto" />
        ) : ts.data.points.length === 0 ? (
          <EmptyState title="No data in this range" />
        ) : (
          <div className="px-1 pt-1">
            <DemandChart
              points={ts.data.points}
              anomalies={prefs.overlay === "on" ? ts.data.anomalies : []}
              showBaseline={prefs.baseline}
              height={360}
            />
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Panel title="Forecast error · daily % variance of recorded sales vs forecast">
          {ts.data ? <ErrorBars points={ts.data.points} height={200} /> : <Skeleton className="m-3 h-[180px] w-auto" />}
        </Panel>
        <Panel title={`Regional comparison · ${prefs.sku}`}>
          {regional.data ? (
            <RegionalBars rows={regional.data} focus={region} height={200} />
          ) : (
            <Skeleton className="m-3 h-[180px] w-auto" />
          )}
        </Panel>
      </div>

      {ts.data && (
        <Panel title={`Anomalies · ${ts.data.anomalies.length}`}>
          {ts.data.anomalies.length === 0 ? (
            <EmptyState title="No anomalies detected for this series" />
          ) : (
            <AnomalyTable rows={ts.data.anomalies} hiddenColumns={["sku_id", "product", "region"]} />
          )}
        </Panel>
      )}

      <IntelPanel>
        <div className="panel-header bg-transparent">Series diagnostics</div>
        <div className="space-y-4 p-3">
          {s ? (
            <>
              <div>
                <div className="label mb-1">Totals ({s.days} days)</div>
                <KV k="Forecast" v={fmtInt(s.forecast_total)} />
                <KV k="Recorded sales" v={fmtInt(s.recorded_sales_total)} />
                <KV k="Variance" v={<span className={(s.variance_pct ?? 0) < 0 ? "text-negative" : "text-positive"}>{fmtPct(s.variance_pct, 2)}</span>} />
              </div>
              <div>
                <div className="label mb-1">Forecast accuracy</div>
                <KV k="MAPE" v={fmtPct(s.mape_pct, 2, false)} />
                <KV k="Bias" v={fmtPct(s.bias_pct, 2)} />
                <KV k="Residual volatility (σ)" v={fmtPct(s.residual_volatility_pct, 2, false)} />
                <KV k="Sales CV" v={fmtPct(s.sales_cv_pct, 1, false)} />
              </div>
              <div>
                <div className="label mb-1">Availability</div>
                <KV k="Stockout days" v={<span className={stockoutDays ? "text-warning" : ""}>{stockoutDays}</span>} />
                <p className="mt-1 text-xs text-subtle">
                  On stockout days recorded sales understate demand; the chart marks an <i>estimated</i> unconstrained demand.
                </p>
              </div>
              {regional.data && (
                <div>
                  <div className="label mb-1">By region</div>
                  {regional.data.map((r) => (
                    <KV
                      key={r.region}
                      k={r.region}
                      v={
                        <>
                          <span className={(r.variance_pct ?? 0) < 0 ? "text-negative" : "text-positive"}>{fmtPct(r.variance_pct, 2)}</span>
                          <span className="text-subtle"> · {r.anomaly_count} anm</span>
                        </>
                      }
                    />
                  ))}
                </div>
              )}
            </>
          ) : (
            <Skeleton className="h-40" />
          )}
        </div>
      </IntelPanel>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <Analytics />
    </Suspense>
  );
}
