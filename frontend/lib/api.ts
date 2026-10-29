import type {
  Anomaly,
  DatasetSpec,
  Envelope,
  EventItem,
  ImportRecord,
  Investigation,
  InvestigationListItem,
  Overview,
  RegionalRow,
  SettingsPayload,
  Sku,
  TimeSeries,
  ValidationSummary,
  Verdict,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

function qs(params?: Params): string {
  if (!params) return "";
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  });
  const out = s.toString();
  return out ? `?${out}` : "";
}

async function request<T>(path: string, init?: RequestInit, params?: Params): Promise<Envelope<T>> {
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}${qs(params)}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the API server. Is the backend running on port 8000?");
  }
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, "bad_response", `Unexpected response from API (${res.status})`);
  }
  if (!res.ok || body.error) {
    const e = body.error ?? { code: "http_error", message: `HTTP ${res.status}` };
    throw new ApiError(res.status, e.code, e.message, e.details);
  }
  return body;
}

const get = async <T>(path: string, params?: Params) => (await request<T>(path, undefined, params)).data;
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => get<{ status: string; llm_available: boolean; model: string }>("/health"),
  overview: () => get<Overview>("/analytics/overview"),
  skus: () => get<Sku[]>("/analytics/skus"),
  regions: () => get<string[]>("/analytics/regions"),
  timeseries: (sku_id: string, region: string, start?: string, end?: string) =>
    get<TimeSeries>("/analytics/timeseries", { sku_id, region, start, end }),
  regional: (sku_id: string, start?: string, end?: string) =>
    get<RegionalRow[]>("/analytics/regional", { sku_id, start, end }),
  portfolio: (region?: string, category?: string) =>
    get<{ points: { date: string; forecast_qty: number; recorded_sales_qty: number }[] }>("/analytics/portfolio", {
      region,
      category,
    }),

  anomalies: async (params: Params) => {
    const r = await request<Anomaly[]>("/anomalies", undefined, params);
    return { rows: r.data, total: (r.meta.total as number) ?? r.data.length };
  },
  anomaly: (id: string) => get<Anomaly & { investigations: InvestigationListItem[] }>(`/anomalies/${id}`),
  detect: async () => (await request<{ created: number; kept_investigated: number }>("/anomalies/detect", json("POST"))).data,

  events: async (params: Params) => {
    const r = await request<EventItem[]>("/events", undefined, params);
    return { rows: r.data, total: (r.meta.total as number) ?? r.data.length, categories: (r.meta.categories as string[]) ?? [] };
  },

  startInvestigation: async (anomaly_id: string, use_llm = true) =>
    (await request<{ investigation_id: string; status: string }>("/investigations", json("POST", { anomaly_id, use_llm }))).data,
  investigations: (anomaly_id?: string) => get<InvestigationListItem[]>("/investigations", { anomaly_id }),
  investigation: (id: string) => get<Investigation>(`/investigations/${id}`),
  feedback: async (hypothesisId: number, verdict: Verdict, note?: string) =>
    (await request<{ id: number }>(`/hypotheses/${hypothesisId}/feedback`, json("POST", { verdict, note }))).data,

  specs: () => get<Record<string, DatasetSpec>>("/datasets/specs"),
  imports: () => get<ImportRecord[]>("/datasets/imports"),
  datasetSummary: () =>
    get<{ counts: Record<string, number>; date_range: [string | null, string | null] }>("/datasets/summary"),
  loadSynthetic: async () =>
    (await request<{ seed: number; imports: { dataset_type: string; status: string; rows_imported: number }[]; anomalies_detected: number }>(
      "/datasets/load-synthetic",
      json("POST"),
    )).data,
  upload: async (type: string, file: File, mode: "preview" | "import") => {
    const fd = new FormData();
    fd.append("file", file);
    return (await request<ValidationSummary>(`/datasets/${type}/${mode}`, { method: "POST", body: fd })).data;
  },

  settings: () => get<SettingsPayload>("/settings"),
  putDetection: async (values: Record<string, number>) =>
    (await request<SettingsPayload>("/settings/detection", json("PUT", values))).data,
  putWeights: async (weights: Record<string, number>) =>
    (await request<SettingsPayload>("/settings/relevance/weights", json("PUT", weights))).data,
  resetSettings: async () => (await request<SettingsPayload>("/settings/reset", json("POST"))).data,
};
