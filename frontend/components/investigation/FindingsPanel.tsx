"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, CircleHelp, Cpu, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { cn, fmtDate, titleCase } from "@/lib/format";
import type { Hypothesis, Investigation, Verdict } from "@/lib/types";
import { Badge, Button, StrengthBadge, Tip } from "../ui";

const VERDICTS: { v: Verdict; label: string; icon: typeof Check; tone: string }[] = [
  { v: "CONFIRMED", label: "Confirmed", icon: Check, tone: "text-positive border-positive/50 bg-positive/10" },
  { v: "PLAUSIBLE", label: "Plausible", icon: CircleHelp, tone: "text-accent border-accent/50 bg-accent/10" },
  { v: "REJECTED", label: "Rejected", icon: X, tone: "text-negative border-negative/50 bg-negative/10" },
  { v: "NEEDS_INVESTIGATION", label: "Needs investigation", icon: ShieldAlert, tone: "text-warning border-warning/50 bg-warning/10" },
];

export function ModeBadge({ inv }: { inv: Pick<Investigation, "analysis_mode" | "model"> }) {
  if (inv.analysis_mode === "llm")
    return (
      <Tip content={`Hypotheses synthesised by ${inv.model} from structured evidence, then validated (evidence IDs, wording).`}>
        <span>
          <Badge tone="cyan">
            <Bot className="h-3 w-3" /> LLM · {inv.model}
          </Badge>
        </span>
      </Tip>
    );
  return (
    <Tip content="Rule-based synthesis from the same evidence. Fully reproducible; no language model involved.">
      <span>
        <Badge tone="muted">
          <Cpu className="h-3 w-3" /> Deterministic
        </Badge>
      </span>
    </Tip>
  );
}

export function FindingsPanel({
  inv,
  onInspect,
}: {
  inv: Investigation;
  onInspect: (h: Hypothesis) => void;
}) {
  return (
    <div className="flex flex-col">
      <div className="panel-header bg-transparent">
        <span>Investigation Findings</span>
        <ModeBadge inv={inv} />
      </div>
      {inv.status === "COMPLETED" && (
        <>
          <div className="border-b border-border px-3 py-3">
            <div className="label mb-1">Summary</div>
            <p className="text-sm leading-5 text-fg">{inv.summary}</p>
          </div>
          <ol className="divide-y divide-border">
            {inv.hypotheses.map((h) => (
              <HypothesisCard key={h.id} h={h} invId={inv.investigation_id} onInspect={() => onInspect(h)} />
            ))}
          </ol>
          {inv.llm_notes.length > 0 && (
            <div className="border-t border-border px-3 py-2.5">
              <div className="label mb-1">Synthesis notes</div>
              <ul className="space-y-0.5 text-xs text-muted">
                {inv.llm_notes.map((n, i) => (
                  <li key={i}>· {n}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {inv.status === "RUNNING" && <div className="p-3 text-sm text-muted">Investigation in progress…</div>}
      {inv.status === "FAILED" && <div className="p-3 text-sm text-negative">Investigation failed: {inv.error}</div>}
    </div>
  );
}

function HypothesisCard({ h, invId, onInspect }: { h: Hypothesis; invId: string; onInspect: () => void }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const latest = h.feedback[h.feedback.length - 1];
  const fb = useMutation({
    mutationFn: (v: Verdict) => api.feedback(h.id, v, note || undefined),
    onSuccess: (_, v) => {
      toast.success(`Feedback saved · ${titleCase(v.toLowerCase())}`);
      setNote("");
      setShowNote(false);
      qc.invalidateQueries({ queryKey: ["investigation", invId] });
      qc.invalidateQueries({ queryKey: ["investigations"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <li className="px-3 py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="font-mono text-xs uppercase tracking-wider text-fg">
          <span className="text-subtle">{String(h.rank).padStart(2, "0")} /</span> {h.title}
        </div>
        <StrengthBadge strength={h.evidence_strength} />
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-2xs text-subtle">
        <span className="font-mono uppercase">Evidence: {h.evidence_strength}</span>
        <span>·</span>
        <span className="uppercase">{h.claim_type === "assumption" ? "Unverified assumption" : "Plausible hypothesis"}</span>
        {h.score != null && (
          <>
            <span>·</span>
            <Tip content="Heuristic support score (relevance + corroboration − contradictions). Not a probability.">
              <span className="cursor-help font-mono underline decoration-dotted">score {h.score.toFixed(2)}</span>
            </Tip>
          </>
        )}
      </div>
      <p className="mt-2 text-sm leading-5 text-muted">{h.explanation}</p>

      <div className="mt-2 flex items-center gap-3 font-mono text-2xs">
        <span className="text-positive">▲ {h.supporting_evidence_ids.length} supporting</span>
        <span className="text-negative">▼ {h.contradicting_evidence_ids.length} contradicting</span>
      </div>

      {h.recommended_actions.length > 0 && (
        <div className="mt-2.5">
          <div className="label mb-1">Recommended next steps</div>
          <ul className="space-y-0.5 text-sm text-fg">
            {h.recommended_actions.map((a, i) => (
              <li key={i} className="flex gap-2">
                <span className="font-mono text-subtle">{i + 1}.</span>
                {a}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 flex items-center gap-1.5">
        <Button size="xs" variant="default" onClick={onInspect} className="font-mono uppercase tracking-wider">
          [ Inspect evidence ]
        </Button>
      </div>

      <div className="mt-3 rounded border border-border bg-bg/60 p-2">
        <div className="flex items-center justify-between">
          <span className="label">Analyst assessment</span>
          {latest && (
            <span className="font-mono text-2xs text-subtle">
              last: <span className="text-fg">{latest.verdict.replace("_", " ")}</span>
              {latest.created_at && ` · ${fmtDate(latest.created_at)}`}
            </span>
          )}
        </div>
        <div className="mt-1.5 grid grid-cols-2 gap-1">
          {VERDICTS.map(({ v, label, icon: Icon, tone }) => (
            <button
              key={v}
              disabled={fb.isPending}
              onClick={() => fb.mutate(v)}
              className={cn(
                "flex h-6 items-center justify-center gap-1 rounded-sm border text-xs transition-colors",
                latest?.verdict === v ? tone : "border-border text-muted hover:border-subtle hover:text-fg",
              )}
            >
              <Icon className="h-3 w-3" /> {label}
            </button>
          ))}
        </div>
        {showNote ? (
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note — saved with the next assessment you select"
            className="input mt-1.5 h-14 w-full resize-none py-1"
          />
        ) : (
          <button onClick={() => setShowNote(true)} className="mt-1.5 text-2xs text-subtle hover:text-fg">
            + add note
          </button>
        )}
        {h.feedback.filter((f) => f.note).length > 0 && (
          <ul className="mt-1.5 space-y-0.5 border-t border-border pt-1.5 text-xs text-muted">
            {h.feedback
              .filter((f) => f.note)
              .map((f) => (
                <li key={f.id}>
                  <span className="font-mono text-2xs text-subtle">{f.verdict.replace("_", " ")}:</span> {f.note}
                </li>
              ))}
          </ul>
        )}
      </div>
    </li>
  );
}
