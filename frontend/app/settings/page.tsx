"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, ErrorState, Panel, SkeletonRows } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, titleCase } from "@/lib/format";

const DETECTION_HELP: Record<string, string> = {
  z_threshold: "|robust z| for a day to be flagged by residual analysis",
  min_daily_variance: "Minimum |daily residual| (fraction) for a flagged day",
  min_run_days: "Consecutive flagged days for a residual anomaly",
  extreme_z: "Single-day anomalies allowed above this |z|",
  reference_window_days: "Frozen reference baseline length (days)",
  reference_lag_days: "Reference ends this many days before the evaluated day",
  cusum_k: "CUSUM allowance (robust-sigma units)",
  cusum_h: "CUSUM decision interval",
  cusum_recovery_days: "In-band days that close a sustained window",
  min_sustained_days: "Minimum length of a sustained (CUSUM) anomaly",
  min_window_variance: "Minimum |window variance| (fraction) to keep any anomaly",
  severity_high: "|variance| at or above this is HIGH",
  severity_medium: "|variance| at or above this is MEDIUM",
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [det, setDet] = useState<Record<string, string>>({});
  const [w, setW] = useState<Record<string, string>>({});

  useEffect(() => {
    if (s.data) {
      setDet(Object.fromEntries(Object.entries(s.data.detection).map(([k, v]) => [k, String(v)])));
      setW(Object.fromEntries(Object.entries(s.data.relevance.weights).map(([k, v]) => [k, String(v)])));
    }
  }, [s.data]);

  const onSaved = (msg: string) => {
    toast.success(msg);
    qc.invalidateQueries({ queryKey: ["settings"] });
  };
  const saveDet = useMutation({
    mutationFn: () => api.putDetection(Object.fromEntries(Object.entries(det).map(([k, v]) => [k, Number(v)]))),
    onSuccess: () => onSaved("Detection thresholds saved — re-run detection to apply"),
    onError: (e: Error) => toast.error(e.message),
  });
  const saveW = useMutation({
    mutationFn: () => api.putWeights(Object.fromEntries(Object.entries(w).map(([k, v]) => [k, Number(v)]))),
    onSuccess: () => onSaved("Relevance weights saved — applies to new investigations"),
    onError: (e: Error) => toast.error(e.message),
  });
  const reset = useMutation({ mutationFn: api.resetSettings, onSuccess: () => onSaved("Settings reset to defaults") });
  const redetect = useMutation({
    mutationFn: api.detect,
    onSuccess: (r) => {
      toast.success(`Detection complete · ${r.created} anomalies`);
      qc.invalidateQueries();
    },
  });

  if (s.isError) return <ErrorState error={s.error} retry={() => s.refetch()} />;
  if (!s.data) return <SkeletonRows rows={12} />;
  const d = s.data;
  const wSum = Object.values(w).reduce((a, b) => a + (Number(b) || 0), 0);

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold">Settings</h1>
          <p className="text-sm text-muted">Detection thresholds, heuristic relevance weights and AI reasoning status.</p>
        </div>
        <Button variant="ghost" onClick={() => reset.mutate()} loading={reset.isPending}>
          Reset to defaults
        </Button>
      </div>

      <Panel title="AI reasoning provider">
        <div className="flex flex-wrap items-center gap-4 p-3 text-sm">
          <Badge tone={d.llm.available ? "cyan" : "muted"}>{d.llm.available ? "LLM mode available" : "Deterministic mode"}</Badge>
          <span className="font-mono text-xs text-muted">
            provider {d.llm.provider} · model {d.llm.model} · effort {d.llm.effort} · key {d.llm.configured ? "configured" : "not configured"}
          </span>
          <span className="text-xs text-subtle">
            Set <code className="font-mono">ANTHROPIC_API_KEY</code> in <code className="font-mono">.env</code> and restart the API to enable LLM
            synthesis. Without it, investigations use the deterministic rule-based engine.
          </span>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Panel
          title="Anomaly detection thresholds"
          actions={
            <>
              <Button size="xs" onClick={() => redetect.mutate()} loading={redetect.isPending}>
                Re-run detection
              </Button>
              <Button size="xs" variant="primary" onClick={() => saveDet.mutate()} loading={saveDet.isPending}>
                Save
              </Button>
            </>
          }
        >
          <table className="table-dense w-full">
            <tbody>
              {Object.entries(det).map(([k, v]) => (
                <tr key={k}>
                  <td className="font-mono text-xs text-fg">{k}</td>
                  <td className="text-xs text-muted">{DETECTION_HELP[k]}</td>
                  <td className="w-28">
                    <input
                      className={cn("input w-full text-right font-mono", Number(v) !== d.detection_defaults[k] && "border-warning/60")}
                      value={v}
                      onChange={(e) => setDet({ ...det, [k]: e.target.value })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel
          title={
            <>
              Event relevance weights <Badge tone="warning">Heuristic — not probabilities</Badge>
            </>
          }
          actions={
            <Button size="xs" variant="primary" onClick={() => saveW.mutate()} loading={saveW.isPending} disabled={Math.abs(wSum - 1) > 1e-6}>
              Save
            </Button>
          }
        >
          <table className="table-dense w-full">
            <tbody>
              {Object.entries(w).map(([k, v]) => (
                <tr key={k} className="align-top">
                  <td className="w-28 py-1.5 font-mono text-xs text-fg">{k}</td>
                  <td className="py-1.5 text-xs text-muted">{d.relevance.components[k]}</td>
                  <td className="w-24 py-1.5">
                    <input className="input w-full text-right font-mono" value={v} onChange={(e) => setW({ ...w, [k]: e.target.value })} />
                  </td>
                </tr>
              ))}
              <tr>
                <td className="font-mono text-xs">Σ</td>
                <td className="text-xs text-subtle">Weights must sum to 1.00</td>
                <td className={cn("text-right font-mono text-sm", Math.abs(wSum - 1) > 1e-6 ? "text-negative" : "text-positive")}>
                  {wSum.toFixed(2)}
                </td>
              </tr>
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel title="Event category → mechanism map (config/relevance.yaml)">
        <table className="table-dense w-full">
          <thead>
            <tr>
              <th>Category</th>
              <th>Driver type</th>
              <th>Mechanism</th>
              <th>Typical direction of recorded sales</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(d.relevance.categories).map(([k, c]) => (
              <tr key={k}>
                <td className="font-mono text-xs">{k}</td>
                <td className="text-xs">{titleCase(c.driver_type)}</td>
                <td className="text-xs text-muted">{c.mechanism.replace(/_/g, " ")}</td>
                <td className="font-mono text-xs">{c.direction}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
