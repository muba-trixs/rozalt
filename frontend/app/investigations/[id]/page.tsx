"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { DemandChart, type TimelineEvent } from "@/components/charts/DemandChart";
import { EvidenceExplorer } from "@/components/investigation/EvidenceExplorer";
import { FindingsPanel, ModeBadge } from "@/components/investigation/FindingsPanel";
import { useStartInvestigation } from "@/components/investigation/InvestigateButton";
import { CandidatesTable, StatisticsView } from "@/components/investigation/Sections";
import { StageList } from "@/components/investigation/StageList";
import { IntelPanel, useShell } from "@/components/shell/AppShell";
import { Badge, Button, ErrorState, Panel, SeverityBadge, Skeleton, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, cn, fmtDate, fmtInt, fmtMs, fmtPct, titleCase } from "@/lib/format";
import type { Hypothesis } from "@/lib/types";

export default function InvestigationPage({ params }: { params: { id: string } }) {
  const id = decodeURIComponent(params.id);
  const qc = useQueryClient();
  const shell = useShell();
  const rerun = useStartInvestigation();
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null);
  const [tab, setTab] = useState("events");
  const [evFilter, setEvFilter] = useState<{ ids: string[]; label: string } | null>(null);
  const tabsRef = useRef<HTMLDivElement>(null);

  const inv = useQuery({
    queryKey: ["investigation", id],
    queryFn: () => api.investigation(id),
    refetchInterval: (q) => (q.state.data?.status === "RUNNING" ? 350 : false),
  });
  const data = inv.data;
  const a = data?.anomaly;

  useEffect(() => {
    if (data && data.status !== "RUNNING") {
      qc.invalidateQueries({ queryKey: ["investigations"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    }
  }, [data?.status, qc, data]);

  const ts = useQuery({
    queryKey: ["timeseries", a?.sku_id, a?.region],
    queryFn: () => api.timeseries(a!.sku_id, a!.region),
    enabled: !!a,
  });

  const events: TimelineEvent[] = useMemo(
    () =>
      (data?.candidates ?? [])
        .filter((c) => c.reasons.above_threshold || c.relevance_score >= 0.2)
        .map((c) => ({
          id: c.source_id,
          title: c.title,
          start: c.event_date,
          end: c.event_end_date ?? c.event_date,
          lane: c.driver_type,
          emphasis: c.reasons.above_threshold ? "candidate" : "screened",
          score: c.relevance_score,
        })),
    [data?.candidates],
  );

  const zoom = useMemo(
    () => (a ? { start: addDays(a.start_date, -45), end: addDays(a.end_date, 21) } : null),
    [a],
  );
  const invWindow = useMemo(() => (a ? { start: a.start_date, end: a.end_date } : null), [a]);
  const otherAnomalies = useMemo(
    () => (ts.data?.anomalies ?? []).filter((x) => x.anomaly_id !== a?.anomaly_id),
    [ts.data, a],
  );

  const inspect = (h: Hypothesis) => {
    setEvFilter({ ids: [...h.supporting_evidence_ids, ...h.contradicting_evidence_ids], label: h.title });
    setTab("evidence");
    tabsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (inv.isError) return <ErrorState error={inv.error} retry={() => inv.refetch()} />;
  if (!data || !a)
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-20" />
        <Skeleton className="h-80" />
      </div>
    );

  const running = data.status === "RUNNING";

  return (
    <div className="space-y-3 p-4">
      {/* Investigation header */}
      <section className="panel">
        <div className="flex flex-wrap items-start justify-between gap-4 px-4 py-3">
          <div className="min-w-0">
            <div className="font-mono text-2xs uppercase tracking-wider text-subtle">
              Rozalt / <Link href="/investigations" className="hover:text-fg">Investigations</Link> /{" "}
              <span className="text-accent">{data.investigation_id}</span>
            </div>
            <h1 className="mt-1 font-mono text-lg font-medium tracking-wide text-fg">
              {a.sku_id} · {a.region.toUpperCase()} · {fmtDate(a.start_date)}
              {a.duration_days > 1 && <span className="text-subtle"> → {fmtDate(a.end_date)}</span>}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
              <span>{a.product_name}</span>
              <span className="text-border">|</span>
              <span>{a.category}</span>
              <span className="text-border">|</span>
              <span className="font-mono text-xs">{a.anomaly_id}</span>
              <span className="text-border">|</span>
              <span className="font-mono text-xs">detector: {a.detection_method}</span>
              <StatusBadge status={data.status} />
              {data.analysis_mode && <ModeBadge inv={data} />}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-sm sm:grid-cols-4">
            <HeaderMetric label="Forecast" value={fmtInt(a.forecast_qty)} />
            <HeaderMetric label="Recorded sales" value={fmtInt(a.recorded_sales_qty)} />
            <HeaderMetric
              label="Variance"
              value={fmtPct(a.variance_pct)}
              tone={a.variance_pct < 0 ? "text-negative" : "text-positive"}
            />
            <div>
              <div className="label">Severity</div>
              <div className="mt-1">
                <SeverityBadge severity={a.severity} />
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-border px-4 py-1.5 text-2xs text-subtle">
          <span className="font-mono">
            {a.duration_days} DAY WINDOW · PEAK z {a.peak_robust_z.toFixed(2)} · {data.created_at?.replace("T", " ").slice(0, 19)} UTC
            {data.timings.total_ms != null && ` · PIPELINE ${fmtMs(data.timings.total_ms)}`}
          </span>
          <Button
            size="xs"
            variant="ghost"
            loading={rerun.isPending}
            disabled={running}
            onClick={() => rerun.mutate({ anomalyId: a.anomaly_id })}
          >
            <RefreshCw className="h-3 w-3" /> Re-run investigation
          </Button>
        </div>
      </section>

      {(running || data.status === "FAILED") && (
        <Panel title={running ? "Investigation in progress" : "Investigation failed"}>
          <div className="p-3">
            <StageList stages={data.stage_log} />
            {data.status === "FAILED" && (
              <div className="mt-2 flex items-center gap-2 rounded border border-negative/40 bg-negative/10 px-3 py-2 text-sm text-negative">
                <AlertTriangle className="h-4 w-4" /> {data.error}
              </div>
            )}
          </div>
        </Panel>
      )}

      {/* Demand chart + synchronized event timeline */}
      <Panel
        title={
          <>
            Forecast vs recorded sales <span className="normal-case tracking-normal text-subtle">· with event timeline</span>
          </>
        }
        actions={
          selectedEvent && (
            <Button size="xs" variant="ghost" onClick={() => setSelectedEvent(null)}>
              Clear highlight · {selectedEvent}
            </Button>
          )
        }
      >
        {ts.isLoading ? (
          <Skeleton className="m-3 h-[380px] w-auto" />
        ) : ts.isError ? (
          <ErrorState error={ts.error} />
        ) : (
          <div className="px-1 pt-1">
            <DemandChart
              points={ts.data!.points}
              anomalies={otherAnomalies}
              investigationWindow={invWindow}
              events={events}
              highlightEventId={selectedEvent}
              onEventClick={(eid) => setSelectedEvent((cur) => (cur === eid ? null : eid))}
              zoomRange={zoom}
              height={330}
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-3 py-1.5 text-2xs text-subtle">
              <span>Recorded sales are bounded by available inventory; ◆ marks estimated unconstrained demand on stockout days (estimate).</span>
              <span className="ml-auto flex items-center gap-3">
                <span className="flex items-center gap-1"><i className="inline-block h-2 w-3 rounded-sm bg-accent/70" /> candidate event</span>
                <span className="flex items-center gap-1"><i className="inline-block h-2 w-3 rounded-sm bg-subtle/50" /> screened, below threshold</span>
                <span className="flex items-center gap-1"><i className="inline-block h-2 w-3 rounded-sm bg-warning" /> selected</span>
              </span>
            </div>
          </div>
        )}
      </Panel>

      {data.status === "COMPLETED" && (
        <div ref={tabsRef} className="scroll-mt-4">
          <Tabs.Root value={tab} onValueChange={setTab} className="panel">
            <Tabs.List className="flex h-9 items-center gap-1 border-b border-border px-2">
              {[
                ["events", `Relevant events · ${data.candidates.filter((c) => c.reasons.above_threshold).length}`],
                ["statistics", "Statistical findings"],
                ["evidence", `Evidence explorer · ${data.evidence.length}`],
                ["limits", `Limitations & pipeline`],
              ].map(([v, l]) => (
                <Tabs.Trigger
                  key={v}
                  value={v}
                  className={cn(
                    "relative h-9 px-3 text-xs font-medium uppercase tracking-wider text-subtle transition-colors hover:text-fg",
                    "data-[state=active]:text-fg data-[state=active]:after:absolute data-[state=active]:after:inset-x-2 data-[state=active]:after:bottom-0 data-[state=active]:after:h-0.5 data-[state=active]:after:bg-accent",
                  )}
                >
                  {l}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            <Tabs.Content value="events">
              <CandidatesTable
                candidates={data.candidates}
                selected={selectedEvent}
                onSelect={(eid) => setSelectedEvent((cur) => (cur === eid ? null : eid))}
              />
            </Tabs.Content>
            <Tabs.Content value="statistics">
              <StatisticsView inv={data} />
            </Tabs.Content>
            <Tabs.Content value="evidence">
              <EvidenceExplorer
                evidence={data.evidence}
                hypotheses={data.hypotheses}
                candidates={data.candidates}
                filterIds={evFilter?.ids ?? null}
                filterLabel={evFilter?.label ?? null}
                onClearFilter={() => setEvFilter(null)}
                onSelectEvent={(eid) => {
                  setSelectedEvent(eid);
                  document.querySelector("main")?.scrollTo({ top: 0, behavior: "smooth" });
                }}
              />
            </Tabs.Content>
            <Tabs.Content value="limits" className="grid grid-cols-1 gap-3 p-3 lg:grid-cols-2">
              <div>
                <div className="label mb-1.5">Data limitations</div>
                <ul className="space-y-1.5 text-sm text-muted">
                  {data.limitations.map((l, i) => (
                    <li key={i} className="flex gap-2">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" /> {l}
                    </li>
                  ))}
                </ul>
                <div className="label mb-1.5 mt-4">Claim classification</div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone="neutral">Verified record</Badge>
                  <Badge tone="blue">Statistical association</Badge>
                  <Badge tone="warning">Estimate / assumption</Badge>
                  <Badge tone="positive">Plausible hypothesis</Badge>
                </div>
                <p className="mt-2 text-xs text-subtle">
                  Hypotheses are associations ranked by evidence; none is a verified cause until an analyst confirms it.
                </p>
              </div>
              <div>
                <div className="label mb-1.5">Pipeline stages ({titleCase(data.analysis_mode ?? "")} synthesis)</div>
                <StageList stages={data.stage_log} />
                {Object.entries(data.timings)
                  .filter(([k]) => k.startsWith("llm_"))
                  .map(([k, v]) => (
                    <div key={k} className="mt-1 flex justify-between px-2 font-mono text-2xs text-subtle">
                      <span>{k}</span>
                      <span>{fmtMs(v)}</span>
                    </div>
                  ))}
              </div>
            </Tabs.Content>
          </Tabs.Root>
        </div>
      )}

      <IntelPanel>
        <FindingsPanel
          inv={data}
          onInspect={(h) => {
            shell.openPanel();
            inspect(h);
          }}
        />
        {running && (
          <div className="border-t border-border p-3">
            <StageList stages={data.stage_log} compact />
          </div>
        )}
      </IntelPanel>
    </div>
  );
}

function HeaderMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={cn("mt-0.5 text-lg num", tone ?? "text-fg")}>{value}</div>
    </div>
  );
}
