"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { IntelPanel } from "@/components/shell/AppShell";
import { Badge, Button, EmptyState, ErrorState, Panel, Segmented, Select, SkeletonRows } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, fmtDate, fmtIso, titleCase } from "@/lib/format";
import { usePersistentState } from "@/lib/hooks";
import type { EventItem } from "@/lib/types";

interface F {
  q: string;
  source_type: "all" | "external" | "operational";
  category: string;
  region: string;
  sort: "date" | "relevance";
}
const EMPTY: F = { q: "", source_type: "all", category: "", region: "", sort: "date" };

export default function EventsPage() {
  const [f, setF] = usePersistentState<F>("di.events.filters", EMPTY);
  const [selected, setSelected] = useState<EventItem | null>(null);
  const regions = useQuery({ queryKey: ["regions"], queryFn: api.regions });
  const q = useQuery({
    queryKey: ["events", f],
    queryFn: () => api.events({ ...f, page_size: 500 }),
    placeholderData: keepPreviousData,
  });
  const detail = useQuery({
    queryKey: ["event", selected?.event_id],
    queryFn: async () => (await fetch(`/api/v1/events/${selected!.event_id}`).then((r) => r.json())).data,
    enabled: !!selected,
  });

  return (
    <div className="space-y-3 p-4">
      <div>
        <h1 className="text-lg font-semibold">Event Intelligence</h1>
        <p className="text-sm text-muted">
          Searchable repository of operational and external events from uploaded datasets.{" "}
          <span className="text-subtle">Live external event monitoring is not implemented in this MVP.</span>
        </p>
      </div>
      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <input className="input w-64" placeholder="Search title, description, source…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
          <Segmented
            value={f.source_type}
            onChange={(v) => setF({ ...f, source_type: v })}
            options={[
              { value: "all", label: "All" },
              { value: "external", label: "External" },
              { value: "operational", label: "Operational" },
            ]}
          />
          <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="w-44">
            <option value="">All categories</option>
            {(q.data?.categories ?? []).map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </Select>
          <Select value={f.region} onChange={(e) => setF({ ...f, region: e.target.value })} className="w-40">
            <option value="">All regions</option>
            {(regions.data ?? []).map((r) => (
              <option key={r}>{r}</option>
            ))}
            <option value="National">National</option>
          </Select>
          <Select value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value as F["sort"] })} className="w-48">
            <option value="date">Sort: most recent</option>
            <option value="relevance">Sort: investigation relevance</option>
          </Select>
          {(f.q || f.category || f.region || f.source_type !== "all") && (
            <Button size="xs" variant="ghost" onClick={() => setF(EMPTY)}>
              <X className="h-3 w-3" /> Clear
            </Button>
          )}
          <span className="ml-auto font-mono text-2xs text-subtle">{q.data?.total ?? 0} events</span>
        </div>
        {q.isError ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : q.isLoading ? (
          <SkeletonRows rows={10} />
        ) : (q.data?.rows.length ?? 0) === 0 ? (
          <EmptyState title="No events match" body="Upload operational or external event CSVs in Data Sources." />
        ) : (
          <table className="table-dense w-full table-fixed">
            <thead>
              <tr>
                <th className="w-[92px]">ID</th>
                <th>Event</th>
                <th className="w-[150px]">Category</th>
                <th className="w-[110px]">Date</th>
                <th className="w-[110px]">Region</th>
                <th className="w-[160px]">Source</th>
                <th className="w-[140px]">Related</th>
                <th className="w-[120px] text-right">Inv. relevance</th>
              </tr>
            </thead>
            <tbody>
              {q.data!.rows.map((e) => (
                <tr
                  key={e.event_id}
                  onClick={() => setSelected(e)}
                  className={cn("cursor-pointer", selected?.event_id === e.event_id && "!bg-accent/10")}
                >
                  <td className="font-mono text-xs text-accent">{e.event_id}</td>
                  <td className="truncate">{e.title}</td>
                  <td>
                    <Badge tone={e.source_type === "operational" ? "warning" : "muted"}>{titleCase(e.category)}</Badge>
                  </td>
                  <td className="font-mono text-xs">{fmtDate(e.date)}</td>
                  <td className="truncate">{e.region}</td>
                  <td className="truncate text-xs text-muted">{e.source}</td>
                  <td className="truncate font-mono text-2xs text-subtle">
                    {e.related_sku_ids.length ? e.related_sku_ids.join(", ") : e.related_category || "—"}
                  </td>
                  <td className="text-right font-mono text-xs">
                    {e.investigation_relevance ? (
                      <span>
                        {e.investigation_relevance.max_relevance.toFixed(2)}
                        <span className="text-subtle"> · {e.investigation_relevance.investigations} inv</span>
                      </span>
                    ) : (
                      <span className="text-subtle">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {selected && (
        <IntelPanel>
          <div className="panel-header bg-transparent">
            <span className="font-mono text-accent">{selected.event_id}</span>
            <button onClick={() => setSelected(null)} className="text-subtle hover:text-fg">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-3 p-3">
            <div>
              <div className="flex flex-wrap gap-1.5">
                <Badge tone={selected.source_type === "operational" ? "warning" : "muted"}>{selected.source_type}</Badge>
                <Badge>{titleCase(selected.category)}</Badge>
                {selected.severity && <Badge tone="muted">severity {selected.severity}</Badge>}
              </div>
              <h2 className="mt-2 text-base font-medium">{selected.title}</h2>
              <p className="mt-1 text-sm leading-5 text-muted">{selected.description}</p>
            </div>
            <div className="grid grid-cols-2 gap-2 font-mono text-xs">
              <div>
                <div className="label">Start</div>
                {fmtIso(selected.date)}
              </div>
              <div>
                <div className="label">End</div>
                {fmtIso(selected.end_date)}
              </div>
              <div>
                <div className="label">Region</div>
                {selected.region}
              </div>
              <div>
                <div className="label">Driver type</div>
                {titleCase(selected.driver_type)}
              </div>
              {selected.facility && (
                <div>
                  <div className="label">Facility</div>
                  {selected.facility}
                </div>
              )}
              <div>
                <div className="label">Related</div>
                {selected.related_sku_ids.join(", ") || selected.related_category || "—"}
              </div>
            </div>
            {selected.source_url && (
              <a href={selected.source_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-accent hover:underline">
                {selected.source} <ExternalLink className="h-3 w-3" />
              </a>
            )}
            <div>
              <div className="label mb-1.5">Appears in investigations</div>
              {detail.isLoading ? (
                <SkeletonRows rows={2} />
              ) : (detail.data?.investigations ?? []).length === 0 ? (
                <div className="text-sm text-subtle">Not yet screened by any investigation.</div>
              ) : (
                <ul className="space-y-1">
                  {detail.data.investigations.map((i: any) => (
                    <li key={i.investigation_id}>
                      <Link
                        href={`/investigations/${i.investigation_id}`}
                        className="flex items-center justify-between rounded border border-border px-2 py-1 text-xs hover:border-subtle"
                      >
                        <span className="font-mono text-accent">{i.investigation_id}</span>
                        <span className="font-mono text-subtle">{i.anomaly_id}</span>
                        <span className="font-mono">
                          rel {i.relevance_score.toFixed(2)} {i.above_threshold ? "· candidate" : "· screened"}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-2xs text-subtle">Relevance is a heuristic ranking, not a probability of causation.</p>
            </div>
          </div>
        </IntelPanel>
      )}
    </div>
  );
}
