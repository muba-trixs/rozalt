"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { DemandChart } from "@/components/charts/DemandChart";
import { AnomalyTable } from "@/components/tables/AnomalyTable";
import { Button, EmptyState, ErrorState, Kpi, Panel, Select, Skeleton, SkeletonRows } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, fmtInt, fmtPct } from "@/lib/format";

export default function OverviewPage() {
  const qc = useQueryClient();
  const ov = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const skus = useQuery({ queryKey: ["skus"], queryFn: api.skus });
  const [series, setSeries] = useState<{ sku_id: string; region: string } | null>(null);

  useEffect(() => {
    if (!series && ov.data?.default_series) setSeries(ov.data.default_series);
  }, [ov.data, series]);

  const ts = useQuery({
    queryKey: ["timeseries", series?.sku_id, series?.region],
    queryFn: () => api.timeseries(series!.sku_id, series!.region),
    enabled: !!series,
  });

  const load = useMutation({
    mutationFn: api.loadSynthetic,
    onSuccess: (r) => {
      toast.success(`Synthetic dataset loaded · ${r.anomalies_detected} anomalies detected`);
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const regions = useMemo(() => skus.data?.find((s) => s.sku_id === series?.sku_id)?.regions ?? [], [skus.data, series]);

  if (ov.isError) return <ErrorState error={ov.error} retry={() => ov.refetch()} />;
  const k = ov.data?.kpis;
  const empty = ov.data && k?.skus_monitored === 0;

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-fg">Rozalt</h1>
          <p className="text-sm text-muted">Monitor demand behavior. Investigate anomalies. Discover hidden drivers.</p>
        </div>
        {ov.data?.date_range[0] && (
          <div className="font-mono text-2xs uppercase tracking-wider text-subtle">
            Data {fmtDate(ov.data.date_range[0])} → {fmtDate(ov.data.date_range[1])}
          </div>
        )}
      </div>

      {empty ? (
        <Panel>
          <EmptyState
            title="No data loaded"
            body="Load the deterministic synthetic FMCG dataset (24 SKUs × 5 regions × 365 days with six injected scenarios) or upload your own CSVs."
            action={
              <div className="flex gap-2">
                <Button variant="primary" loading={load.isPending} onClick={() => load.mutate()}>
                  <Database className="h-3.5 w-3.5" /> Load synthetic dataset
                </Button>
                <Link href="/data">
                  <Button>Upload CSVs</Button>
                </Link>
              </div>
            }
          />
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {k ? (
              <>
                <Kpi label="SKUs monitored" value={fmtInt(k.skus_monitored)} sub={`${k.regions_monitored} regions`} />
                <Kpi
                  label="Active anomalies"
                  value={fmtInt(k.active_anomalies)}
                  sub={
                    <span className="font-mono">
                      <span className="text-negative">▼ {k.negative_anomalies}</span> ·{" "}
                      <span className="text-positive">▲ {k.positive_anomalies}</span> · {k.uninvestigated} uninvestigated
                    </span>
                  }
                />
                <Kpi label="High-severity deviations" value={fmtInt(k.high_severity)} tone="negative" sub="|variance| ≥ 25% over window" />
                <Kpi label="Completed investigations" value={fmtInt(k.completed_investigations)} sub="persisted reports" />
              </>
            ) : (
              Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[74px]" />)
            )}
          </div>

          <Panel
            title={
              <>
                Forecast vs recorded sales
                {ts.data && (
                  <span className="font-mono normal-case tracking-normal text-subtle">
                    · {ts.data.sku_id} {ts.data.product_name} · {ts.data.region} · period variance{" "}
                    {fmtPct(ts.data.summary.variance_pct, 2)} · MAPE {fmtPct(ts.data.summary.mape_pct, 1, false)}
                  </span>
                )}
              </>
            }
            actions={
              <>
                <Select
                  value={series?.sku_id ?? ""}
                  onChange={(e) => setSeries((s) => ({ sku_id: e.target.value, region: s?.region ?? "" }))}
                  className="w-56"
                >
                  {(skus.data ?? []).map((s) => (
                    <option key={s.sku_id} value={s.sku_id}>
                      {s.sku_id} · {s.product_name}
                    </option>
                  ))}
                </Select>
                <Select
                  value={series?.region ?? ""}
                  onChange={(e) => setSeries((s) => ({ sku_id: s?.sku_id ?? "", region: e.target.value }))}
                  className="w-36"
                >
                  {regions.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </Select>
              </>
            }
          >
            {ts.isLoading || !series ? (
              <Skeleton className="m-3 h-[320px] w-auto" />
            ) : ts.isError ? (
              <ErrorState error={ts.error} retry={() => ts.refetch()} />
            ) : (
              <div className="px-1 pt-1">
                <DemandChart points={ts.data!.points} anomalies={ts.data!.anomalies} height={330} />
              </div>
            )}
          </Panel>

          <Panel
            title="Highest-priority anomalies"
            actions={
              <Link href="/anomalies" className="text-xs text-accent hover:underline">
                Open Anomaly Explorer →
              </Link>
            }
          >
            {ov.isLoading ? (
              <SkeletonRows rows={8} />
            ) : (ov.data?.top_anomalies.length ?? 0) === 0 ? (
              <EmptyState title="No anomalies detected" body="Detection thresholds can be adjusted in Settings." />
            ) : (
              <AnomalyTable rows={ov.data!.top_anomalies} hiddenColumns={["anomaly_id", "forecast", "recorded"]} />
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
