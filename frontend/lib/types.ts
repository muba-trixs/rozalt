// Shared API types — mirror the FastAPI response payloads.

export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type Direction = "NEGATIVE" | "POSITIVE";
export type Strength = "STRONG" | "MODERATE" | "WEAK" | "INSUFFICIENT";
export type Verdict = "CONFIRMED" | "PLAUSIBLE" | "REJECTED" | "NEEDS_INVESTIGATION";

export interface Envelope<T> {
  data: T;
  meta: Record<string, unknown> & { total?: number; page?: number; page_size?: number };
  error: { code: string; message: string; details?: unknown } | null;
}

export interface Anomaly {
  anomaly_id: string;
  sku_id: string;
  product_name: string | null;
  category: string | null;
  region: string;
  start_date: string;
  end_date: string;
  peak_date: string;
  duration_days: number;
  forecast_qty: number;
  recorded_sales_qty: number;
  variance_pct: number;
  peak_robust_z: number;
  direction: Direction;
  severity: Severity;
  detection_method: string;
  status: "NEW" | "INVESTIGATING" | "INVESTIGATED";
  details: Record<string, unknown>;
  latest_investigation_id?: string | null;
  latest_investigation_status?: string | null;
}

export interface Overview {
  kpis: {
    skus_monitored: number;
    regions_monitored: number;
    active_anomalies: number;
    high_severity: number;
    uninvestigated: number;
    completed_investigations: number;
    negative_anomalies: number;
    positive_anomalies: number;
  };
  top_anomalies: Anomaly[];
  default_series: { sku_id: string; region: string } | null;
  date_range: [string | null, string | null];
}

export interface SeriesPoint {
  date: string;
  forecast_qty: number;
  recorded_sales_qty: number;
  seasonal_baseline: number | null;
  rolling_mean_28: number | null;
  rolling_std_28: number | null;
  forecast_error: number;
  variance_pct: number | null;
  available_inventory?: number | null;
  stockout_flag?: boolean | null;
  estimated_unconstrained_demand?: number | null;
}

export interface SeriesSummary {
  forecast_total: number;
  recorded_sales_total: number;
  variance_pct: number | null;
  mape_pct: number | null;
  bias_pct: number | null;
  residual_volatility_pct: number | null;
  sales_cv_pct: number | null;
  days: number;
}

export interface TimeSeries {
  sku_id: string;
  product_name: string;
  category: string | null;
  region: string;
  points: SeriesPoint[];
  summary: SeriesSummary;
  anomalies: Anomaly[];
  quantity_definitions: Record<string, string>;
}

export interface Sku {
  sku_id: string;
  product_name: string;
  category: string | null;
  brand: string | null;
  regions: string[];
}

export interface RegionalRow extends SeriesSummary {
  region: string;
  anomaly_count: number;
}

export interface StageEntry {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at?: string;
  duration_ms?: number;
  detail?: string;
  error?: string;
}

export interface Candidate {
  rank: number;
  source_table: string;
  source_id: string;
  driver_type: string;
  title: string;
  event_date: string;
  event_end_date: string | null;
  region: string;
  relevance_score: number;
  components: Record<string, number>;
  reasons: Record<string, unknown> & { above_threshold?: boolean; description?: string; category?: string };
}

export interface EvidenceTarget {
  role: "supporting" | "contradicting";
  weight: number;
}

export interface Evidence {
  evidence_id: string;
  kind: "fact" | "statistical" | "context";
  polarity: "supporting" | "contradicting" | "neutral" | "mixed";
  driver_types: string[];
  source_table: string | null;
  source_id: string | null;
  title: string;
  description: string;
  payload: Record<string, unknown> & { targets?: Record<string, EvidenceTarget>; statistics?: Record<string, unknown> };
}

export interface Feedback {
  id: number;
  verdict: Verdict;
  note: string | null;
  created_at: string | null;
}

export interface Hypothesis {
  id: number;
  rank: number;
  title: string;
  driver_type: string;
  evidence_strength: Strength;
  claim_type: string;
  explanation: string;
  recommended_actions: string[];
  score: number | null;
  generated_by: "llm" | "deterministic";
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  feedback: Feedback[];
}

export interface Investigation {
  investigation_id: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  analysis_mode: "llm" | "deterministic" | null;
  model: string | null;
  summary: string | null;
  limitations: string[];
  llm_notes: string[];
  error: string | null;
  stage_log: StageEntry[];
  timings: Record<string, number>;
  created_at: string | null;
  completed_at: string | null;
  anomaly: Anomaly;
  statistics: Record<string, any>;
  candidates: Candidate[];
  evidence: Evidence[];
  hypotheses: Hypothesis[];
}

export interface InvestigationListItem {
  investigation_id: string;
  anomaly_id: string;
  status: string;
  analysis_mode: string | null;
  summary: string | null;
  sku_id: string;
  product_name: string | null;
  region: string;
  start_date: string;
  variance_pct: number;
  severity: Severity;
  direction: Direction;
  top_hypothesis: { title: string; evidence_strength: Strength; driver_type: string } | null;
  hypotheses: number;
  feedback_count: number;
  created_at: string | null;
  total_ms: number | null;
}

export interface EventItem {
  event_id: string;
  source_type: "external" | "operational";
  title: string;
  description: string;
  category: string;
  driver_type: string;
  date: string;
  end_date: string;
  region: string;
  source: string | null;
  source_url: string | null;
  related_sku_ids: string[];
  related_category: string | null;
  severity: string | null;
  facility: string | null;
  investigation_relevance: { max_relevance: number; investigations: number } | null;
}

export interface ImportRecord {
  id: number;
  dataset_type: string;
  filename: string;
  status: "SUCCESS" | "PARTIAL" | "FAILED";
  rows_total: number;
  rows_imported: number;
  rows_rejected: number;
  rows_duplicate: number;
  errors: { row?: number; column?: string; value?: string; message: string }[];
  created_at: string | null;
}

export interface ValidationSummary {
  dataset_type: string;
  columns: string[];
  missing_columns: string[];
  unexpected_columns: string[];
  rows_total: number;
  rows_valid: number;
  rows_rejected: number;
  rows_duplicate_in_file: number;
  errors: { row: number; column: string; value: string; message: string }[];
  errors_truncated: boolean;
  fatal: string | null;
  preview: Record<string, unknown>[];
  filename?: string;
  status?: string;
  rows_imported?: number;
  rows_duplicate_in_db?: number;
  detection?: { created: number; kept_investigated: number };
}

export interface DatasetSpec {
  required: string[];
  optional: string[];
  description: string;
  key: string[];
  order: number;
}

export interface SettingsPayload {
  detection: Record<string, number>;
  detection_defaults: Record<string, number>;
  relevance: {
    weights: Record<string, number>;
    components: Record<string, string>;
    window: Record<string, number>;
    categories: Record<string, { driver_type: string; mechanism: string; direction: string }>;
    hypothesis: Record<string, number>;
  };
  llm: { configured: boolean; enabled: boolean; available: boolean; provider: string; model: string; effort: string };
}
