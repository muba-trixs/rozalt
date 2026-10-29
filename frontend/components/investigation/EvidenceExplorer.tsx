"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { cn, fmtIso, titleCase } from "@/lib/format";
import type { Candidate, Evidence, Hypothesis } from "@/lib/types";
import { Badge, Segmented } from "../ui";

const KIND_LABEL: Record<Evidence["kind"], string> = {
  fact: "Verified record",
  statistical: "Statistical association",
  context: "Estimate / assumption",
};
const KIND_TONE = { fact: "neutral", statistical: "blue", context: "warning" } as const;

export function PolarityBadge({ p }: { p: Evidence["polarity"] }) {
  const tone = p === "supporting" ? "positive" : p === "contradicting" ? "negative" : p === "mixed" ? "warning" : "muted";
  return <Badge tone={tone}>{p}</Badge>;
}

export function EvidenceExplorer({
  evidence,
  hypotheses,
  candidates,
  filterIds,
  filterLabel,
  onClearFilter,
  onSelectEvent,
}: {
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  candidates: Candidate[];
  filterIds: string[] | null;
  filterLabel: string | null;
  onClearFilter: () => void;
  onSelectEvent: (id: string) => void;
}) {
  const [kind, setKind] = useState<"all" | Evidence["kind"]>("all");
  const [selected, setSelected] = useState<Evidence | null>(null);

  const rows = useMemo(
    () =>
      evidence.filter((e) => (kind === "all" || e.kind === kind) && (!filterIds || filterIds.includes(e.evidence_id))),
    [evidence, kind, filterIds],
  );

  const roleFor = (e: Evidence): "supporting" | "contradicting" | null => {
    if (!filterLabel) return null;
    const h = hypotheses.find((x) => x.title === filterLabel);
    if (!h) return null;
    if (h.supporting_evidence_ids.includes(e.evidence_id)) return "supporting";
    if (h.contradicting_evidence_ids.includes(e.evidence_id)) return "contradicting";
    return null;
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <Segmented
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: `All ${evidence.length}` },
            { value: "fact", label: "Verified records" },
            { value: "statistical", label: "Statistical" },
            { value: "context", label: "Estimates / assumptions" },
          ]}
        />
        {filterIds && (
          <span className="flex items-center gap-1.5 rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-xs text-accent">
            Cited by: {filterLabel}
            <button onClick={onClearFilter} className="hover:text-fg" aria-label="Clear filter">
              <X className="h-3 w-3" />
            </button>
          </span>
        )}
        <span className="ml-auto font-mono text-2xs text-subtle">{rows.length} items</span>
      </div>
      <table className="table-dense w-full">
        <thead>
          <tr>
            <th className="w-[150px]">Evidence ID</th>
            <th className="w-[150px]">Classification</th>
            <th>Finding</th>
            <th className="w-[110px]">Polarity</th>
            <th className="w-[100px]">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => {
            const role = roleFor(e);
            return (
              <tr key={e.evidence_id} onClick={() => setSelected(e)} className="cursor-pointer align-top">
                <td className="py-1.5 font-mono text-xs text-accent">{e.evidence_id.split("-").slice(-2).join("-")}</td>
                <td className="py-1.5">
                  <Badge tone={KIND_TONE[e.kind]}>{KIND_LABEL[e.kind]}</Badge>
                </td>
                <td className="py-1.5">
                  <div className="text-sm text-fg">{e.title}</div>
                  <div className="line-clamp-2 text-xs text-muted">{e.description}</div>
                </td>
                <td className="py-1.5">
                  {role ? <PolarityBadge p={role} /> : <PolarityBadge p={e.polarity} />}
                </td>
                <td className="py-1.5 font-mono text-2xs text-subtle">{e.source_id ?? e.source_table ?? "derived"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <EvidenceDrawer
        e={selected}
        onClose={() => setSelected(null)}
        hypotheses={hypotheses}
        candidates={candidates}
        onSelectEvent={(id) => {
          setSelected(null);
          onSelectEvent(id);
        }}
      />
    </div>
  );
}

function EvidenceDrawer({
  e,
  onClose,
  hypotheses,
  candidates,
  onSelectEvent,
}: {
  e: Evidence | null;
  onClose: () => void;
  hypotheses: Hypothesis[];
  candidates: Candidate[];
  onSelectEvent: (id: string) => void;
}) {
  const cited = e
    ? hypotheses.filter(
        (h) => h.supporting_evidence_ids.includes(e.evidence_id) || h.contradicting_evidence_ids.includes(e.evidence_id),
      )
    : [];
  const source = e?.source_id ? candidates.find((c) => c.source_id === e.source_id) : undefined;
  const stats = e?.payload?.statistics as Record<string, unknown> | undefined;
  const targets = e?.payload?.targets ?? {};

  return (
    <Dialog.Root open={!!e} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="fixed right-0 top-0 z-50 flex h-full w-[560px] max-w-[95vw] flex-col border-l border-border bg-surface shadow-2xl focus:outline-none">
          {e && (
            <>
              <div className="flex h-11 items-center justify-between border-b border-border px-4">
                <Dialog.Title className="font-mono text-sm text-accent">{e.evidence_id}</Dialog.Title>
                <Dialog.Close className="text-subtle hover:text-fg">
                  <X className="h-4 w-4" />
                </Dialog.Close>
              </div>
              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
                <div>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge tone={KIND_TONE[e.kind]}>{KIND_LABEL[e.kind]}</Badge>
                    <PolarityBadge p={e.polarity} />
                  </div>
                  <h3 className="mt-2 text-base font-medium text-fg">{e.title}</h3>
                  <Dialog.Description className="mt-1 text-sm leading-5 text-muted">{e.description}</Dialog.Description>
                </div>

                {Object.keys(targets).length > 0 && (
                  <section>
                    <div className="label mb-1.5">Bearing on candidate drivers</div>
                    <ul className="space-y-1">
                      {Object.entries(targets).map(([k, t]) => (
                        <li key={k} className="flex items-center justify-between rounded border border-border px-2 py-1 text-xs">
                          <span className="font-mono text-fg">{k.split(":")[1]}</span>
                          <span className="flex items-center gap-2">
                            <span className="font-mono text-subtle">weight {t.weight.toFixed(2)}</span>
                            <PolarityBadge p={t.role} />
                          </span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {cited.length > 0 && (
                  <section>
                    <div className="label mb-1.5">Cited by hypotheses</div>
                    <ul className="space-y-1 text-sm">
                      {cited.map((h) => (
                        <li key={h.id} className="flex items-center justify-between">
                          <span>
                            {String(h.rank).padStart(2, "0")} / {h.title}
                          </span>
                          <PolarityBadge p={h.supporting_evidence_ids.includes(e.evidence_id) ? "supporting" : "contradicting"} />
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {source && (
                  <section>
                    <div className="label mb-1.5">Source record · {source.source_table}</div>
                    <div className="rounded border border-border bg-bg p-2.5 text-sm">
                      <div className="font-mono text-xs text-accent">{source.source_id}</div>
                      <div className="mt-0.5 text-fg">{source.title}</div>
                      <div className="mt-1 text-xs text-muted">{String(source.reasons.description ?? "")}</div>
                      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-2xs text-subtle">
                        <span>DATE {fmtIso(source.event_date)} → {fmtIso(source.event_end_date)}</span>
                        <span>REGION {source.region}</span>
                        <span>CATEGORY {String(source.reasons.category ?? "")}</span>
                        <span>SOURCE {String(source.reasons.source ?? "—")}</span>
                      </div>
                      <button
                        onClick={() => onSelectEvent(source.source_id)}
                        className="mt-2 text-xs text-accent hover:underline"
                      >
                        Highlight on demand chart →
                      </button>
                    </div>
                  </section>
                )}

                {stats && (
                  <section>
                    <div className="label mb-1.5">Statistical calculation</div>
                    <StatTable stats={stats} />
                  </section>
                )}
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function StatTable({ stats }: { stats: Record<string, unknown> }) {
  const scalar = Object.entries(stats).filter(([, v]) => v === null || ["string", "number", "boolean"].includes(typeof v));
  const lists = Object.entries(stats).filter(([k, v]) => Array.isArray(v) && (k === "assumptions" || k === "caveats"));
  const nested = Object.entries(stats).filter(
    ([k, v]) => v && typeof v === "object" && !(k === "assumptions" || k === "caveats") && k !== "targets",
  );
  return (
    <div className="space-y-2">
      <table className="w-full text-xs">
        <tbody>
          {scalar.map(([k, v]) => (
            <tr key={k} className="border-b border-border/60">
              <td className="py-1 pr-3 text-muted">{titleCase(k)}</td>
              <td className={cn("py-1 text-right font-mono num", typeof v === "boolean" && (v ? "text-warning" : "text-subtle"))}>
                {v === null ? "—" : typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(4)) : String(v)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {lists.map(([k, v]) => (
        <div key={k}>
          <div className="label mb-0.5">{titleCase(k)}</div>
          <ul className="space-y-0.5 text-xs text-muted">
            {(v as string[]).map((x, i) => (
              <li key={i}>· {x}</li>
            ))}
          </ul>
        </div>
      ))}
      {nested.map(([k, v]) => (
        <details key={k} className="rounded border border-border">
          <summary className="cursor-pointer px-2 py-1 text-xs text-muted">{titleCase(k)}</summary>
          <pre className="max-h-64 overflow-auto px-2 pb-2 font-mono text-2xs text-subtle">{JSON.stringify(v, null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}
