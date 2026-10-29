"use client";

import { cn, fmtIso, fmtNum, fmtPct, titleCase } from "@/lib/format";
import type { Candidate, Investigation } from "@/lib/types";
import { Badge, Tip } from "../ui";
import { StatTable } from "./EvidenceExplorer";

const COMPONENTS = ["temporal", "geographic", "product", "operational", "magnitude"] as const;

export function CandidatesTable({
  candidates,
  selected,
  onSelect,
}: {
  candidates: Candidate[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-xs text-muted">
        <Badge tone="warning">Heuristic</Badge>
        Relevance ranks events for review using configurable weights — it is <b className="text-fg">not</b> a probability that
        an event caused the deviation.
      </div>
      <table className="table-dense w-full">
        <thead>
          <tr>
            <th className="w-10">#</th>
            <th className="w-[96px]">Event</th>
            <th>Title</th>
            <th className="w-[150px]">Driver type</th>
            <th className="w-[96px]">Start</th>
            <th className="w-[110px]">Region</th>
            <th className="w-[150px]">Components T·G·P·O·M</th>
            <th className="w-[84px] text-right">Relevance</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => {
            const above = !!c.reasons.above_threshold;
            return (
              <tr
                key={c.source_id}
                onClick={() => onSelect(c.source_id)}
                className={cn("cursor-pointer", selected === c.source_id && "!bg-warning/10", !above && "opacity-60")}
              >
                <td className="font-mono text-xs text-subtle">{c.rank}</td>
                <td className="font-mono text-xs text-accent">{c.source_id}</td>
                <td className="max-w-0 truncate text-sm">
                  <Tip
                    content={
                      <div className="space-y-0.5">
                        {COMPONENTS.map((k) => (
                          <div key={k}>
                            <b className="font-mono">{k[0].toUpperCase()}</b> {fmtNum(c.components[k])} — {String(c.reasons[k] ?? "")}
                          </div>
                        ))}
                      </div>
                    }
                  >
                    <span>{c.title}</span>
                  </Tip>
                </td>
                <td className="text-xs text-muted">{titleCase(c.driver_type)}</td>
                <td className="font-mono text-xs">{fmtIso(c.event_date)}</td>
                <td className="text-xs">{c.region}</td>
                <td>
                  <div className="flex items-end gap-0.5" aria-label="relevance components">
                    {COMPONENTS.map((k) => (
                      <div key={k} className="flex w-6 flex-col items-center">
                        <div className="h-3 w-full overflow-hidden rounded-[1px] bg-elevated">
                          <div className="h-full bg-accent/70" style={{ width: `${(c.components[k] ?? 0) * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </td>
                <td className="text-right font-mono text-sm num">
                  <span className={above ? "text-fg" : "text-subtle"}>{c.relevance_score.toFixed(2)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StatBlock({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="rounded border border-border bg-bg/50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="label text-muted">{title}</div>
        {note && <span className="text-2xs text-subtle">{note}</span>}
      </div>
      {children}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className={cn("font-mono text-base num", tone)}>{value}</div>
    </div>
  );
}

export function StatisticsView({ inv }: { inv: Investigation }) {
  const s = inv.statistics;
  if (!s?.context) return <div className="p-4 text-sm text-muted">No statistics recorded.</div>;
  const wc = s.context.window_comparison;
  const pr = s.peer_regions;
  const pc = s.peer_category;
  const invn = s.inventory;
  const tone = (v: number | null | undefined) => (v == null ? "" : v < 0 ? "text-negative" : "text-positive");

  return (
    <div className="space-y-3 p-3">
      <div className="text-xs text-muted">
        All results are <b className="text-fg">exploratory</b>: p-values are descriptive, comparison-group methods assume
        parallel behaviour that is not tested, and none of these statistics establishes causation.
      </div>
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <StatBlock title="Anomaly window vs preceding 28 days" note={wc?.method}>
          {wc?.insufficient_data ? (
            <div className="text-sm text-warning">Insufficient data: {wc.reason}</div>
          ) : (
            <div className="grid grid-cols-4 gap-3">
              <Metric label="Pre mean resid." value={fmtPct(wc.pre_mean_residual_pct)} />
              <Metric label="Window mean" value={fmtPct(wc.during_mean_residual_pct)} tone={tone(wc.during_mean_residual_pct)} />
              <Metric label="Welch t / p" value={`${fmtNum(wc.t_statistic)} / ${wc.p_value?.toExponential?.(1) ?? "—"}`} />
              <Metric label="Cohen's d" value={fmtNum(wc.cohens_d)} />
            </div>
          )}
        </StatBlock>

        <StatBlock title="Availability & inventory" note={invn?.method}>
          {invn?.insufficient_data ? (
            <div className="text-sm text-warning">{invn.reason}</div>
          ) : (
            <div className="grid grid-cols-4 gap-3">
              <Metric
                label="Stockout days"
                value={`${invn.stockout_days_in_window} / ${invn.window_days}`}
                tone={invn.stockout_days_in_window > 0 ? "text-warning" : ""}
              />
              <Metric label="Coverage Δ" value={fmtPct(invn.coverage_change_pct)} tone={tone(invn.coverage_change_pct)} />
              <Metric label="Spearman ρ" value={fmtNum(invn.spearman_inventory_vs_sales?.rho)} />
              <Metric
                label="Supply constraint"
                value={invn.supply_constraint_observed ? "OBSERVED" : "NOT OBSERVED"}
                tone={invn.supply_constraint_observed ? "text-warning" : "text-subtle"}
              />
              {invn.estimated_unserved_units != null && (
                <div className="col-span-4 rounded border border-warning/30 bg-warning/5 px-2 py-1 text-xs text-warning">
                  ESTIMATE: ~{Math.round(invn.estimated_unserved_units).toLocaleString()} units of demand may have gone unserved on
                  stockout days. Underlying demand is not observed.
                </div>
              )}
            </div>
          )}
        </StatBlock>

        {[
          { t: `Comparison group · ${pr?.comparison_group ?? ""}`, d: pr },
          { t: `Comparison group · ${pc?.comparison_group ?? ""}`, d: pc },
        ].map(({ t, d }) => (
          <StatBlock key={t} title={t} note={d?.method}>
            {d?.insufficient_data ? (
              <div className="text-sm text-warning">{d.reason ?? "Insufficient data"}</div>
            ) : (
              <>
                <div className="grid grid-cols-4 gap-3">
                  <Metric label="Focal Δ (pp)" value={fmtNum(d.focal_change_pct_points, 1)} tone={tone(d.focal_change_pct_points)} />
                  <Metric label="Comparison Δ" value={fmtNum(d.comparison_mean_change_pct_points, 1)} />
                  <Metric label="DiD (pp)" value={fmtNum(d.did_estimate_pct_points, 1)} tone={tone(d.did_estimate_pct_points)} />
                  <Metric label="Pattern" value={(d.pattern ?? "—").toUpperCase()} />
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {(d.comparison_series ?? []).map((g: any) => (
                    <span key={g.group} className="rounded-sm border border-border px-1.5 py-0.5 font-mono text-2xs text-muted">
                      {g.group} <span className={tone(g.change_pct_points)}>{fmtNum(g.change_pct_points, 1)}</span>
                    </span>
                  ))}
                </div>
              </>
            )}
          </StatBlock>
        ))}
      </div>

      {Object.keys(s.event_windows ?? {}).length > 0 && (
        <StatBlock title="Event-window comparisons (per candidate)" note="welch_t_test_on_daily_residuals">
          <table className="table-dense w-full">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Window</th>
                <th className="text-right">Onset lag</th>
                <th className="text-right">Pre</th>
                <th className="text-right">During</th>
                <th className="text-right">Δ pp</th>
                <th className="text-right">p</th>
                <th className="text-right">n</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(s.event_windows).map(([k, w]: [string, any]) => (
                <tr key={k}>
                  <td className="font-mono text-xs text-accent">{k.split(":")[1]}</td>
                  <td className="font-mono text-xs">{w.event_window?.join(" → ")}</td>
                  <td className="text-right font-mono text-xs">{w.onset_lag_days}d</td>
                  {w.insufficient_data ? (
                    <td colSpan={5} className="text-right text-xs text-warning">
                      insufficient data
                    </td>
                  ) : (
                    <>
                      <td className="text-right font-mono text-xs">{fmtPct(w.pre_mean_residual_pct)}</td>
                      <td className={cn("text-right font-mono text-xs", tone(w.during_mean_residual_pct))}>{fmtPct(w.during_mean_residual_pct)}</td>
                      <td className="text-right font-mono text-xs">{fmtNum(w.difference_pct_points, 1)}</td>
                      <td className="text-right font-mono text-xs">{w.p_value?.toExponential?.(1)}</td>
                      <td className="text-right font-mono text-xs">
                        {w.n_pre}/{w.n_during}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </StatBlock>
      )}

      {Object.keys(s.history ?? {}).length > 0 && (
        <StatBlock title="Historical consistency" note="prior_same_category_event_windows">
          <ul className="space-y-1 text-xs">
            {Object.entries(s.history).map(([k, h]: [string, any]) => (
              <li key={k} className="flex justify-between gap-2">
                <span className="font-mono text-accent">{k.split(":")[1]}</span>
                <span className="text-muted">
                  {h.insufficient_data
                    ? "No prior events of this category in the region — insufficient history"
                    : `${h.n_with_similar_deviation} of ${h.n_prior_events} prior ${titleCase(h.category).toLowerCase()} events coincided with a similar deviation`}
                </span>
              </li>
            ))}
          </ul>
        </StatBlock>
      )}

      <details className="rounded border border-border">
        <summary className="cursor-pointer px-3 py-2 text-xs text-muted">Raw statistics payload</summary>
        <div className="p-3">
          <StatTable stats={s} />
        </div>
      </details>
    </div>
  );
}
