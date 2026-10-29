"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Badge, EmptyState, ErrorState, Panel, SeverityBadge, SkeletonRows, StatusBadge, StrengthBadge, Variance } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, fmtMs } from "@/lib/format";

export default function InvestigationsPage() {
  const q = useQuery({ queryKey: ["investigations"], queryFn: () => api.investigations() });
  const [search, setSearch] = useState("");
  const rows = useMemo(() => {
    const s = search.toLowerCase();
    return (q.data ?? []).filter((r) =>
      !s ? true : `${r.investigation_id} ${r.anomaly_id} ${r.sku_id} ${r.region} ${r.top_hypothesis?.title ?? ""}`.toLowerCase().includes(s),
    );
  }, [q.data, search]);

  return (
    <div className="space-y-3 p-4">
      <div>
        <h1 className="text-lg font-semibold">Investigations</h1>
        <p className="text-sm text-muted">Saved investigation reports. Open any report to review evidence and record feedback.</p>
      </div>
      <Panel>
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <input className="input w-72" placeholder="Search investigations…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <span className="ml-auto font-mono text-2xs text-subtle">{rows.length} reports</span>
        </div>
        {q.isError ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : q.isLoading ? (
          <SkeletonRows rows={8} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No investigations yet"
            body={
              <>
                Pick an anomaly in the{" "}
                <Link className="text-accent hover:underline" href="/anomalies">
                  Anomaly Explorer
                </Link>{" "}
                and press Investigate.
              </>
            }
          />
        ) : (
          <table className="table-dense w-full table-fixed">
            <thead>
              <tr>
                <th className="w-[92px]">ID</th>
                <th className="w-[92px]">Anomaly</th>
                <th className="w-[84px]">SKU</th>
                <th className="w-[110px]">Region</th>
                <th className="w-[110px]">Date</th>
                <th className="w-[90px] text-right">Variance</th>
                <th className="w-[92px]">Severity</th>
                <th>Leading hypothesis</th>
                <th className="w-[124px]">Evidence</th>
                <th className="w-[110px]">Mode</th>
                <th className="w-[96px]">Status</th>
                <th className="w-[70px] text-right">Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.investigation_id} className="cursor-pointer">
                  <td>
                    <Link href={`/investigations/${r.investigation_id}`} className="font-mono text-xs text-accent hover:underline">
                      {r.investigation_id}
                    </Link>
                  </td>
                  <td className="font-mono text-xs text-subtle">{r.anomaly_id}</td>
                  <td className="font-mono text-xs">{r.sku_id}</td>
                  <td className="truncate">{r.region}</td>
                  <td className="font-mono text-xs">{fmtDate(r.start_date)}</td>
                  <td className="text-right">
                    <Variance value={r.variance_pct} className="text-xs" />
                  </td>
                  <td>
                    <SeverityBadge severity={r.severity} />
                  </td>
                  <td className="truncate">
                    <Link href={`/investigations/${r.investigation_id}`} className="hover:text-accent">
                      {r.top_hypothesis?.title ?? "—"}
                    </Link>
                    {r.feedback_count > 0 && <span className="ml-2 font-mono text-2xs text-subtle">· {r.feedback_count} feedback</span>}
                  </td>
                  <td>{r.top_hypothesis && <StrengthBadge strength={r.top_hypothesis.evidence_strength} />}</td>
                  <td>
                    <Badge tone={r.analysis_mode === "llm" ? "cyan" : "muted"}>{r.analysis_mode ?? "—"}</Badge>
                  </td>
                  <td>
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="text-right font-mono text-xs text-subtle">{fmtMs(r.total_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
