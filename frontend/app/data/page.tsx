"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, FileUp, Upload, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, EmptyState, ErrorState, Panel, Select, SkeletonRows } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, fmtInt, titleCase } from "@/lib/format";
import type { ValidationSummary } from "@/lib/types";

const TYPES = ["demand", "inventory", "promotions", "operational_events", "external_events"];

export default function DataPage() {
  const qc = useQueryClient();
  const specs = useQuery({ queryKey: ["specs"], queryFn: api.specs });
  const summary = useQuery({ queryKey: ["dataset-summary"], queryFn: api.datasetSummary });
  const imports = useQuery({ queryKey: ["imports"], queryFn: api.imports });
  const [type, setType] = useState("demand");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ValidationSummary | null>(null);
  const [result, setResult] = useState<ValidationSummary | null>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const doPreview = useMutation({
    mutationFn: (f: File) => api.upload(type, f, "preview"),
    onSuccess: (r) => {
      setPreview(r);
      setResult(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const doImport = useMutation({
    mutationFn: (f: File) => api.upload(type, f, "import"),
    onSuccess: (r) => {
      setResult(r);
      toast[r.status === "FAILED" ? "error" : "success"](
        `${titleCase(type)} import ${r.status}: ${fmtInt(r.rows_imported)} rows imported` +
          (r.detection ? ` · detection found ${r.detection.created} anomalies` : ""),
      );
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const synthetic = useMutation({
    mutationFn: api.loadSynthetic,
    onSuccess: (r) => {
      toast.success(`Synthetic dataset loaded · ${r.anomalies_detected} anomalies detected`);
      qc.invalidateQueries();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const pick = (f: File | undefined | null) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".csv")) {
      toast.error("Only .csv files are supported");
      return;
    }
    setFile(f);
    doPreview.mutate(f);
  };

  const spec = specs.data?.[type];
  const counts = summary.data?.counts;

  return (
    <div className="space-y-3 p-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold">Data Sources</h1>
          <p className="text-sm text-muted">Upload CSV datasets. Files are validated, normalised and de-duplicated before import.</p>
        </div>
        <Button variant="primary" loading={synthetic.isPending} onClick={() => synthetic.mutate()}>
          <Database className="h-3.5 w-3.5" /> Load synthetic dataset
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        {[
          ["Products", counts?.products],
          ["Regions", counts?.regions],
          ["Demand rows", counts?.demand_records],
          ["Inventory rows", counts?.inventory_records],
          ["Promotions", counts?.promotions],
          ["Operational events", counts?.operational_events],
          ["External events", counts?.external_events],
        ].map(([l, v]) => (
          <div key={l as string} className="panel px-3 py-2">
            <div className="label">{l}</div>
            <div className="mt-0.5 font-mono text-base num">{fmtInt(v as number | undefined)}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="Upload dataset">
          <div className="space-y-3 p-3">
            <div className="flex items-center gap-2">
              <span className="label">Dataset type</span>
              <Select
                value={type}
                onChange={(e) => {
                  setType(e.target.value);
                  setPreview(null);
                  setResult(null);
                  setFile(null);
                }}
                className="w-52"
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {titleCase(t)}
                  </option>
                ))}
              </Select>
              <a href={`/api/v1/datasets/template/${type}`} className="ml-auto text-xs text-accent hover:underline">
                Download template
              </a>
            </div>
            {spec && (
              <div className="rounded border border-border bg-bg/60 px-3 py-2 text-xs">
                <div className="text-muted">{spec.description}</div>
                <div className="mt-1 font-mono">
                  <span className="text-subtle">required: </span>
                  {spec.required.join(", ")}
                </div>
                {spec.optional.length > 0 && (
                  <div className="font-mono">
                    <span className="text-subtle">optional: </span>
                    {spec.optional.join(", ")}
                  </div>
                )}
                <div className="font-mono">
                  <span className="text-subtle">duplicate key: </span>
                  {spec.key.join(" + ")}
                </div>
              </div>
            )}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                pick(e.dataTransfer.files?.[0]);
              }}
              onClick={() => input.current?.click()}
              className={cn(
                "flex h-32 cursor-pointer flex-col items-center justify-center gap-1.5 rounded border border-dashed text-sm transition-colors",
                drag ? "border-accent bg-accent/5 text-fg" : "border-border text-muted hover:border-subtle",
              )}
            >
              <FileUp className="h-5 w-5" />
              {file ? (
                <span className="font-mono text-xs text-fg">
                  {file.name} · {(file.size / 1024).toFixed(1)} KB
                </span>
              ) : (
                <span>Drop a CSV here or click to browse</span>
              )}
              <input
                ref={input}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => {
                  pick(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </div>

            {doPreview.isPending && <SkeletonRows rows={3} />}
            {preview && <ValidationReport v={preview} />}
            {preview && !preview.fatal && (
              <div className="flex items-center gap-2">
                <Button variant="primary" loading={doImport.isPending} onClick={() => file && doImport.mutate(file)} disabled={!!result}>
                  <Upload className="h-3.5 w-3.5" /> Import {fmtInt(preview.rows_valid)} valid rows
                </Button>
                {preview.rows_rejected > 0 && (
                  <span className="text-xs text-warning">{preview.rows_rejected} invalid rows will be skipped and reported.</span>
                )}
              </div>
            )}
            {result && (
              <div
                className={cn(
                  "flex items-center gap-2 rounded border px-3 py-2 text-sm",
                  result.status === "FAILED" ? "border-negative/40 bg-negative/10 text-negative" : "border-positive/40 bg-positive/10 text-positive",
                )}
              >
                {result.status === "FAILED" ? <XCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                {result.status}: {fmtInt(result.rows_imported)} imported · {result.rows_rejected} rejected ·{" "}
                {(result.rows_duplicate_in_file ?? 0) + (result.rows_duplicate_in_db ?? 0)} duplicates skipped
                {result.detection && ` · ${result.detection.created} anomalies detected`}
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Import history">
          {imports.isError ? (
            <ErrorState error={imports.error} />
          ) : imports.isLoading ? (
            <SkeletonRows rows={6} />
          ) : (imports.data ?? []).length === 0 ? (
            <EmptyState title="No imports yet" />
          ) : (
            <ul className="max-h-[520px] divide-y divide-border overflow-y-auto">
              {imports.data!.map((r) => (
                <li key={r.id} className="px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs text-fg">{r.filename}</span>
                    <Badge tone={r.status === "SUCCESS" ? "positive" : r.status === "PARTIAL" ? "warning" : "negative"}>{r.status}</Badge>
                  </div>
                  <div className="mt-0.5 flex justify-between font-mono text-2xs text-subtle">
                    <span>{titleCase(r.dataset_type)}</span>
                    <span>
                      {fmtInt(r.rows_imported)}/{fmtInt(r.rows_total)} · {r.rows_rejected} rej · {r.rows_duplicate} dup
                    </span>
                  </div>
                  {r.errors.length > 0 && (
                    <div className="mt-1 truncate text-2xs text-negative">
                      {r.errors[0].row ? `row ${r.errors[0].row}: ` : ""}
                      {r.errors[0].message}
                      {r.errors.length > 1 && ` (+${r.errors.length - 1} more)`}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function ValidationReport({ v }: { v: ValidationSummary }) {
  return (
    <div className="space-y-2">
      {v.fatal ? (
        <div className="flex items-center gap-2 rounded border border-negative/40 bg-negative/10 px-3 py-2 text-sm text-negative">
          <XCircle className="h-4 w-4" /> {v.fatal}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {[
            ["Rows", v.rows_total, ""],
            ["Valid", v.rows_valid, "text-positive"],
            ["Rejected", v.rows_rejected, v.rows_rejected ? "text-negative" : ""],
            ["Duplicates in file", v.rows_duplicate_in_file, v.rows_duplicate_in_file ? "text-warning" : ""],
          ].map(([l, n, c]) => (
            <div key={l as string} className="rounded border border-border px-2 py-1.5">
              <div className="label">{l}</div>
              <div className={cn("font-mono text-base num", c as string)}>{fmtInt(n as number)}</div>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        {v.columns.map((c) => (
          <Badge key={c} tone={v.unexpected_columns.includes(c) ? "warning" : "muted"}>
            {c}
          </Badge>
        ))}
        {v.missing_columns.map((c) => (
          <Badge key={c} tone="negative">
            missing: {c}
          </Badge>
        ))}
      </div>
      {v.unexpected_columns.length > 0 && (
        <div className="text-xs text-warning">Unrecognised columns will be ignored: {v.unexpected_columns.join(", ")}</div>
      )}
      {v.errors.length > 0 && (
        <div className="max-h-40 overflow-y-auto rounded border border-border">
          <table className="table-dense w-full">
            <thead>
              <tr>
                <th className="w-16">Row</th>
                <th className="w-40">Column</th>
                <th className="w-32">Value</th>
                <th>Problem</th>
              </tr>
            </thead>
            <tbody>
              {v.errors.map((e, i) => (
                <tr key={i}>
                  <td className="font-mono text-xs">{e.row}</td>
                  <td className="font-mono text-xs">{e.column}</td>
                  <td className="truncate font-mono text-xs text-negative">{e.value || "∅"}</td>
                  <td className="text-xs text-muted">{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {v.preview.length > 0 && (
        <div className="overflow-x-auto rounded border border-border">
          <div className="label px-2 py-1">Preview (first {v.preview.length} normalised rows)</div>
          <table className="table-dense w-full">
            <thead>
              <tr>
                {Object.keys(v.preview[0]).map((k) => (
                  <th key={k}>{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {v.preview.map((r, i) => (
                <tr key={i}>
                  {Object.values(r).map((x, j) => (
                    <td key={j} className="whitespace-nowrap font-mono text-xs">
                      {x === null ? "—" : Array.isArray(x) ? x.join(";") : String(x)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
