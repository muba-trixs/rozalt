"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { SeverityBadge, SkeletonRows, StrengthBadge, Variance } from "../ui";

/** Default content of the right Intelligence Panel when a page does not provide its own. */
export function DefaultIntelFeed() {
  const ov = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const invs = useQuery({ queryKey: ["investigations"], queryFn: () => api.investigations() });
  const pending = (ov.data?.top_anomalies ?? []).filter((a) => !a.latest_investigation_id).slice(0, 6);

  return (
    <div className="flex flex-col">
      <div className="panel-header bg-transparent">Intelligence Feed</div>
      <section className="border-b border-border p-3">
        <div className="label mb-2">Awaiting investigation</div>
        {ov.isLoading ? (
          <SkeletonRows rows={3} />
        ) : pending.length === 0 ? (
          <div className="text-sm text-subtle">All high-priority anomalies have been investigated.</div>
        ) : (
          <ul className="space-y-1.5">
            {pending.map((a) => (
              <li key={a.anomaly_id}>
                <Link
                  href={`/anomalies?focus=${a.anomaly_id}`}
                  className="flex items-center gap-2 rounded border border-border bg-surface px-2 py-1.5 hover:border-subtle"
                >
                  <SeverityBadge severity={a.severity} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-mono text-xs text-fg">
                      {a.sku_id} · {a.region.toUpperCase()}
                    </div>
                    <div className="truncate text-2xs text-subtle">{fmtDate(a.start_date)} · {a.duration_days}d</div>
                  </div>
                  <Variance value={a.variance_pct} className="text-xs" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="p-3">
        <div className="label mb-2">Recent investigations</div>
        {invs.isLoading ? (
          <SkeletonRows rows={3} />
        ) : (invs.data ?? []).length === 0 ? (
          <div className="text-sm text-subtle">No investigations yet. Select an anomaly and press Investigate.</div>
        ) : (
          <ul className="space-y-1.5">
            {invs.data!.slice(0, 8).map((i) => (
              <li key={i.investigation_id}>
                <Link
                  href={`/investigations/${i.investigation_id}`}
                  className="block rounded border border-border bg-surface px-2 py-1.5 hover:border-subtle"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-accent">{i.investigation_id}</span>
                    {i.top_hypothesis && <StrengthBadge strength={i.top_hypothesis.evidence_strength} />}
                  </div>
                  <div className="mt-0.5 truncate text-sm text-fg">{i.top_hypothesis?.title ?? i.status}</div>
                  <div className="truncate font-mono text-2xs text-subtle">
                    {i.sku_id} · {i.region} · {fmtDate(i.start_date)}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
