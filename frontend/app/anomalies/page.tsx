"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { SortingState } from "@tanstack/react-table";
import { RefreshCw, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { AnomalyTable } from "@/components/tables/AnomalyTable";
import { Button, EmptyState, ErrorState, Panel, Select, SkeletonRows } from "@/components/ui";
import { api } from "@/lib/api";
import { usePersistentState } from "@/lib/hooks";

interface Filters {
  q: string;
  sku_id: string;
  region: string;
  severity: string;
  direction: string;
  status: string;
  start: string;
  end: string;
}
const EMPTY: Filters = { q: "", sku_id: "", region: "", severity: "", direction: "", status: "", start: "", end: "" };
const PAGE_SIZE = 25;

function AnomalyExplorer() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const focus = params.get("focus");
  const [filters, setFilters] = usePersistentState<Filters>("di.anomalies.filters", EMPTY);
  const [sorting, setSorting] = usePersistentState<SortingState>("di.anomalies.sort", [{ id: "start_date", desc: true }]);
  const [page, setPage] = useState(1);

  const skus = useQuery({ queryKey: ["skus"], queryFn: api.skus });
  const regions = useQuery({ queryKey: ["regions"], queryFn: api.regions });
  const sort = sorting[0] ?? { id: "start_date", desc: true };

  const q = useQuery({
    queryKey: ["anomalies", filters, sort, page],
    queryFn: () =>
      api.anomalies({ ...filters, sort: sort.id, order: sort.desc ? "desc" : "asc", page, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });

  useEffect(() => setPage(1), [filters, sort.id, sort.desc]);

  // When arriving with ?focus=ANM-…, clear filters so the row is reachable and scroll to it.
  const focusQ = useQuery({ queryKey: ["anomaly", focus], queryFn: () => api.anomaly(focus!), enabled: !!focus });
  useEffect(() => {
    if (focusQ.data) {
      setFilters({ ...EMPTY, q: focusQ.data.anomaly_id });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusQ.data]);

  const detect = useMutation({
    mutationFn: api.detect,
    onSuccess: (r) => {
      toast.success(`Detection complete · ${r.created} anomalies (${r.kept_investigated} investigated kept)`);
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setFilters((f) => ({ ...f, [k]: e.target.value }));
  const active = Object.values(filters).some(Boolean);
  const total = q.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold">Anomaly Explorer</h1>
          <p className="text-sm text-muted">
            Deviations of recorded sales from forecast flagged by robust residual z-scores and CUSUM level-shift detection.
          </p>
        </div>
        <Button onClick={() => detect.mutate()} loading={detect.isPending}>
          <RefreshCw className="h-3.5 w-3.5" /> Re-run detection
        </Button>
      </div>

      <Panel>
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
          <input className="input w-56" placeholder="Search ID, SKU, product, region…" value={filters.q} onChange={set("q")} />
          <Select value={filters.sku_id} onChange={set("sku_id")} className="w-44">
            <option value="">All SKUs</option>
            {(skus.data ?? []).map((s) => (
              <option key={s.sku_id} value={s.sku_id}>
                {s.sku_id} · {s.product_name}
              </option>
            ))}
          </Select>
          <Select value={filters.region} onChange={set("region")} className="w-36">
            <option value="">All regions</option>
            {(regions.data ?? []).map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
          <Select value={filters.severity} onChange={set("severity")} className="w-36">
            <option value="">All severities</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </Select>
          <Select value={filters.direction} onChange={set("direction")} className="w-36">
            <option value="">Any direction</option>
            <option value="NEGATIVE">▼ Negative</option>
            <option value="POSITIVE">▲ Positive</option>
          </Select>
          <Select value={filters.status} onChange={set("status")} className="w-40">
            <option value="">Any status</option>
            <option value="NEW">Not investigated</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="INVESTIGATED">Investigated</option>
          </Select>
          <input type="date" className="input w-36 shrink-0 font-mono" value={filters.start} onChange={set("start")} aria-label="From" />
          <span className="text-subtle">→</span>
          <input type="date" className="input w-36 shrink-0 font-mono" value={filters.end} onChange={set("end")} aria-label="To" />
          {active && (
            <Button size="xs" variant="ghost" onClick={() => setFilters(EMPTY)}>
              <X className="h-3 w-3" /> Clear
            </Button>
          )}
          <span className="ml-auto font-mono text-2xs text-subtle">{total} anomalies</span>
        </div>
        {q.isError ? (
          <ErrorState error={q.error} retry={() => q.refetch()} />
        ) : q.isLoading ? (
          <SkeletonRows rows={10} />
        ) : (q.data?.rows.length ?? 0) === 0 ? (
          <EmptyState title="No anomalies match these filters" />
        ) : (
          <AnomalyTable rows={q.data!.rows} sorting={sorting} onSortingChange={setSorting} focusId={focus} />
        )}
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-subtle">
          <span className="font-mono">
            Page {page} / {pages}
          </span>
          <div className="flex gap-1">
            <Button size="xs" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Prev
            </Button>
            <Button size="xs" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <AnomalyExplorer />
    </Suspense>
  );
}
