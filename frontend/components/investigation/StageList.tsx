"use client";

import { Check, Circle, Loader2, X } from "lucide-react";
import { cn, fmtMs } from "@/lib/format";
import type { StageEntry } from "@/lib/types";

/** Renders the persisted backend stage log — every row reflects a real pipeline stage. */
export function StageList({ stages, compact = false }: { stages: StageEntry[]; compact?: boolean }) {
  return (
    <ol className="space-y-px font-mono text-xs">
      {stages.map((s) => (
        <li
          key={s.key}
          className={cn(
            "flex items-center gap-2.5 rounded-sm px-2",
            compact ? "h-6" : "h-7",
            s.status === "running" && "bg-accent/10",
            s.status === "failed" && "bg-negative/10",
          )}
        >
          <span className="flex w-5 shrink-0 justify-center">
            {s.status === "completed" && <Check className="h-3.5 w-3.5 text-positive" />}
            {s.status === "running" && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />}
            {s.status === "failed" && <X className="h-3.5 w-3.5 text-negative" />}
            {s.status === "pending" && <Circle className="h-2.5 w-2.5 text-border" />}
          </span>
          <span
            className={cn(
              "flex-1 truncate",
              s.status === "pending" ? "text-subtle" : s.status === "failed" ? "text-negative" : "text-fg",
            )}
          >
            {s.label}
            {!compact && s.detail && <span className="ml-2 text-subtle">· {s.detail}</span>}
            {s.error && <span className="ml-2 text-negative">· {s.error}</span>}
          </span>
          <span className="w-14 shrink-0 text-right text-subtle">{s.duration_ms != null ? fmtMs(s.duration_ms) : ""}</span>
        </li>
      ))}
    </ol>
  );
}
