"use client";

import * as RTooltip from "@radix-ui/react-tooltip";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "@/lib/format";
import type { Severity, Strength } from "@/lib/types";

type Variant = "primary" | "default" | "ghost" | "danger";

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "xs" | "sm"; loading?: boolean }
>(function Button({ className, variant = "default", size = "sm", loading, children, disabled, ...p }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded border font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-7 px-2.5 text-sm" : "h-6 px-2 text-xs",
        variant === "primary" && "border-accent/60 bg-accent/15 text-accent hover:bg-accent/25",
        variant === "default" && "border-border bg-elevated text-fg hover:border-subtle hover:bg-[#292e36]",
        variant === "ghost" && "border-transparent bg-transparent text-muted hover:bg-elevated hover:text-fg",
        variant === "danger" && "border-negative/50 bg-negative/10 text-negative hover:bg-negative/20",
        className,
      )}
      {...p}
    >
      {loading && <Loader2 className="h-3 w-3 animate-spin" />}
      {children}
    </button>
  );
});

export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-[18px] items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 font-mono text-2xs font-medium uppercase tracking-wide",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

type Tone = "neutral" | "blue" | "cyan" | "positive" | "negative" | "warning" | "muted";
const TONES: Record<Tone, string> = {
  neutral: "border-border bg-elevated text-fg",
  muted: "border-border bg-transparent text-muted",
  blue: "border-accent/40 bg-accent/10 text-accent",
  cyan: "border-cyan/40 bg-cyan/10 text-cyan",
  positive: "border-positive/40 bg-positive/10 text-positive",
  negative: "border-negative/40 bg-negative/10 text-negative",
  warning: "border-warning/40 bg-warning/10 text-warning",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const tone: Tone = severity === "HIGH" ? "negative" : severity === "MEDIUM" ? "warning" : "muted";
  return (
    <Badge tone={tone}>
      <span className={cn("h-1.5 w-1.5 rounded-full", severity === "HIGH" ? "bg-negative" : severity === "MEDIUM" ? "bg-warning" : "bg-subtle")} />
      {severity}
    </Badge>
  );
}

export function StrengthBadge({ strength }: { strength: Strength }) {
  const tone: Tone =
    strength === "STRONG" ? "positive" : strength === "MODERATE" ? "blue" : strength === "WEAK" ? "warning" : "muted";
  const bars = strength === "STRONG" ? 3 : strength === "MODERATE" ? 2 : strength === "WEAK" ? 1 : 0;
  return (
    <Badge tone={tone}>
      <span className="flex items-end gap-px" aria-hidden>
        {[1, 2, 3].map((i) => (
          <span key={i} className={cn("w-[3px] rounded-[1px]", i <= bars ? "bg-current" : "bg-current/25")} style={{ height: 3 + i * 2 }} />
        ))}
      </span>
      {strength}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge tone="muted">NOT INVESTIGATED</Badge>;
  const tone: Tone =
    status === "COMPLETED" || status === "INVESTIGATED" ? "cyan" : status === "FAILED" ? "negative" : status === "RUNNING" || status === "INVESTIGATING" ? "blue" : "muted";
  const label = status === "NEW" ? "NOT INVESTIGATED" : status;
  return <Badge tone={tone}>{label}</Badge>;
}

export function Variance({ value, className }: { value: number | null | undefined; className?: string }) {
  if (value === null || value === undefined) return <span className="text-subtle">—</span>;
  return (
    <span className={cn("font-mono num", value < 0 ? "text-negative" : value > 0 ? "text-positive" : "text-muted", className)}>
      {value > 0 ? "▲ +" : value < 0 ? "▼ " : ""}
      {value.toFixed(1)}%
    </span>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("panel flex min-w-0 flex-col", className)}>
      {title !== undefined && (
        <header className="panel-header">
          <div className="flex min-w-0 items-center gap-2 truncate">{title}</div>
          {actions && <div className="flex shrink-0 items-center gap-1.5 normal-case tracking-normal">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "negative" | "positive" | "warning" }) {
  return (
    <div className="panel px-3 py-2.5">
      <div className="label">{label}</div>
      <div
        className={cn(
          "mt-1 font-mono text-[22px] font-medium leading-7 num",
          tone === "negative" ? "text-negative" : tone === "positive" ? "text-positive" : tone === "warning" ? "text-warning" : "text-fg",
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-subtle">{sub}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4 w-full", className)} />;
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-6" />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <Inbox className="h-5 w-5 text-subtle" />
      <div className="text-sm font-medium text-fg">{title}</div>
      {body && <div className="max-w-md text-sm text-muted">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <AlertTriangle className="h-5 w-5 text-negative" />
      <div className="text-sm font-medium text-fg">Something went wrong</div>
      <div className="max-w-md font-mono text-xs text-muted">{msg}</div>
      {retry && (
        <Button size="xs" onClick={retry} className="mt-2">
          Retry
        </Button>
      )}
    </div>
  );
}

export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn("input shrink-0 cursor-pointer pr-6", className)} {...p}>
      {children}
    </select>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div className="inline-flex h-7 items-center rounded border border-border bg-bg p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-full rounded-sm px-2 text-xs font-medium transition-colors",
            value === o.value ? "bg-elevated text-fg" : "text-muted hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <RTooltip.Root delayDuration={250}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content
          sideOffset={4}
          className="z-50 max-w-xs rounded border border-border bg-elevated px-2 py-1.5 text-xs text-fg shadow-lg"
        >
          {content}
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono num", className)}>{children}</span>;
}

export function KV({ k, v, className }: { k: ReactNode; v: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-3 py-1", className)}>
      <span className="label shrink-0">{k}</span>
      <span className="truncate text-right font-mono text-sm num">{v}</span>
    </div>
  );
}
