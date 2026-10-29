"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Activity, Box, CornerDownLeft, Database, FileSearch, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { NAV } from "./AppShell";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const skus = useQuery({ queryKey: ["skus"], queryFn: api.skus, enabled: open });
  const anomalies = useQuery({
    queryKey: ["anomalies", "palette"],
    queryFn: () => api.anomalies({ page_size: 200, sort: "severity", order: "desc" }),
    enabled: open,
  });
  const invs = useQuery({ queryKey: ["investigations"], queryFn: () => api.investigations(), enabled: open });

  const go = (href: string) => {
    onOpenChange(false);
    router.push(href);
  };

  const item =
    "flex h-8 cursor-pointer items-center gap-2.5 rounded px-2 text-sm text-muted aria-selected:bg-elevated aria-selected:text-fg";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-[14%] z-50 w-[620px] max-w-[92vw] -translate-x-1/2 overflow-hidden rounded-md border border-border bg-surface shadow-2xl">
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Command loop className="flex flex-col">
            <Command.Input
              autoFocus
              placeholder="Type a command, SKU, region or anomaly ID…"
              className="h-11 border-b border-border bg-transparent px-4 text-base text-fg placeholder:text-subtle focus:outline-none"
            />
            <Command.List className="max-h-[420px] overflow-y-auto p-1.5">
              <Command.Empty className="px-3 py-6 text-center text-sm text-subtle">No results.</Command.Empty>
              <Command.Group heading="Navigate" className="[&_[cmdk-group-heading]]:label [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
                {NAV.map((n) => (
                  <Command.Item key={n.href} value={`go ${n.label}`} onSelect={() => go(n.href)} className={item}>
                    <n.icon className="h-4 w-4" strokeWidth={1.75} />
                    <span className="flex-1">{n.label}</span>
                    <span className="font-mono text-2xs text-subtle">g {n.key}</span>
                  </Command.Item>
                ))}
              </Command.Group>
              <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:label [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
                <Command.Item
                  value="load synthetic dataset demo"
                  className={item}
                  onSelect={async () => {
                    onOpenChange(false);
                    const t = toast.loading("Loading synthetic dataset…");
                    try {
                      const r = await api.loadSynthetic();
                      toast.success(`Synthetic data loaded · ${r.anomalies_detected} anomalies detected`, { id: t });
                      qc.invalidateQueries();
                    } catch (e) {
                      toast.error((e as Error).message, { id: t });
                    }
                  }}
                >
                  <Database className="h-4 w-4" /> Load synthetic dataset
                </Command.Item>
                <Command.Item
                  value="re-run anomaly detection"
                  className={item}
                  onSelect={async () => {
                    onOpenChange(false);
                    try {
                      const r = await api.detect();
                      toast.success(`Detection complete · ${r.created} anomalies`);
                      qc.invalidateQueries();
                    } catch (e) {
                      toast.error((e as Error).message);
                    }
                  }}
                >
                  <RefreshCw className="h-4 w-4" /> Re-run anomaly detection
                </Command.Item>
              </Command.Group>
              {(anomalies.data?.rows.length ?? 0) > 0 && (
                <Command.Group heading="Anomalies" className="[&_[cmdk-group-heading]]:label [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
                  {anomalies.data!.rows.map((a) => (
                    <Command.Item
                      key={a.anomaly_id}
                      value={`${a.anomaly_id} ${a.sku_id} ${a.product_name} ${a.region}`}
                      className={item}
                      onSelect={() =>
                        go(a.latest_investigation_id ? `/investigations/${a.latest_investigation_id}` : `/anomalies?focus=${a.anomaly_id}`)
                      }
                    >
                      <Activity className={a.direction === "NEGATIVE" ? "h-4 w-4 text-negative" : "h-4 w-4 text-positive"} />
                      <span className="font-mono text-xs text-fg">{a.anomaly_id}</span>
                      <span className="flex-1 truncate">
                        {a.sku_id} · {a.region} · {fmtDate(a.start_date)}
                      </span>
                      <span className="font-mono text-xs">{a.variance_pct.toFixed(1)}%</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              {(invs.data?.length ?? 0) > 0 && (
                <Command.Group heading="Investigations" className="[&_[cmdk-group-heading]]:label [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
                  {invs.data!.slice(0, 50).map((i) => (
                    <Command.Item
                      key={i.investigation_id}
                      value={`${i.investigation_id} ${i.sku_id} ${i.region} ${i.top_hypothesis?.title ?? ""}`}
                      className={item}
                      onSelect={() => go(`/investigations/${i.investigation_id}`)}
                    >
                      <FileSearch className="h-4 w-4" />
                      <span className="font-mono text-xs text-fg">{i.investigation_id}</span>
                      <span className="flex-1 truncate">
                        {i.sku_id} · {i.region} — {i.top_hypothesis?.title ?? i.status}
                      </span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              {(skus.data?.length ?? 0) > 0 && (
                <Command.Group heading="SKUs" className="[&_[cmdk-group-heading]]:label [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5">
                  {skus.data!.map((s) => (
                    <Command.Item
                      key={s.sku_id}
                      value={`${s.sku_id} ${s.product_name} ${s.category}`}
                      className={item}
                      onSelect={() => go(`/analytics?sku=${s.sku_id}`)}
                    >
                      <Box className="h-4 w-4" />
                      <span className="font-mono text-xs text-fg">{s.sku_id}</span>
                      <span className="flex-1 truncate">{s.product_name}</span>
                      <span className="text-xs text-subtle">{s.category}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
            <div className="flex h-8 items-center gap-3 border-t border-border px-3 text-2xs text-subtle">
              <span className="flex items-center gap-1">
                <CornerDownLeft className="h-3 w-3" /> select
              </span>
              <span>↑↓ navigate</span>
              <span>esc close</span>
            </div>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
