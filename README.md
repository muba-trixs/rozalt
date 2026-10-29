# Rozalt — AI demand anomaly investigation MVP

Given an unexpected deviation of recorded sales from forecast, the platform detects it, discovers
candidate internal and external events, runs exploratory statistics, builds identifiable evidence,
and produces ranked, evidence-backed hypotheses — or says **"Insufficient evidence to identify a
likely driver."** when the data does not support one.

```
Demand data → Anomaly detection → Event discovery → Exploratory statistics → Evidence → Hypotheses (rules or Claude) → Validation → Report → Analyst feedback
```

## Quick start (Windows PowerShell)

Prerequisites: Python 3.10+, Node.js 20+.

```powershell
git clone https://github.com/muba-trixs/rozalt.git
cd rozalt
.\run.ps1 -Setup      # venv, deps, DB migration, synthetic data, frontend build (one time)
.\run.ps1             # API on :8000 and web app on :3000, each in its own window
```

Open http://localhost:3000. API docs: http://127.0.0.1:8000/docs.

If script execution is blocked, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

Manual equivalent:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python -m backend.cli init-db          # alembic upgrade head
.\.venv\Scripts\python -m backend.cli load-synthetic   # generate + import + detect
.\.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000
# second terminal
cd frontend; npm install; npm run build; npm run start  # or: npm run dev
```

Other commands: `.\run.ps1 -Dev` (hot reload), `.\run.ps1 -Test`, `.\run.ps1 -Evaluate`.

### LLM mode (optional)

Set `ANTHROPIC_API_KEY` in `.env` and restart the API. Hypotheses are then synthesised by
`claude-opus-5-5` (configurable via `LLM_MODEL`, `LLM_EFFORT`) through `client.beta.messages.parse`
with a Pydantic output schema and server-side refusal fallbacks. Every LLM report is validated:
cited evidence IDs must exist, roles must match the evidence, explanations may not use
causal-certainty language or confidence percentages. Invalid output is retried once with the
validation errors, then the investigation falls back to the deterministic engine. Each report is
labelled **LLM** or **DETERMINISTIC** in the UI.

## Demo walkthrough

1. **Overview** — KPIs, forecast vs recorded sales, highest-priority anomalies.
2. Press **Investigate** on `SKU-201 · Telangana` (transport strike with an overlapping promotion).
3. The **Investigation Workspace** shows the real pipeline stages, the chart with the investigation
   window and a synchronized event timeline (click an event bar to highlight it), ranked findings
   in the right panel, and tabs for candidate events, statistics, the evidence explorer and limitations.
4. **[ INSPECT EVIDENCE ]** filters the evidence explorer to the hypothesis' citations; click a row
   for source records, statistical calculations, assumptions and caveats.
5. Record an analyst verdict (Confirmed / Plausible / Rejected / Needs investigation); reopen it
   later from **Investigations**.
6. Try `SKU-503 · Delhi NCR` — an injected dip with no cause: the system reports insufficient evidence.

Keyboard: `Ctrl+K` command palette · `g o/a/x/i/e/d/s` navigate · `[` sidebar · `]` intelligence panel.

## Synthetic scenarios (seed 42, 24 SKUs × 5 regions × 365 days)

| ID | Scenario | Hardening |
|----|----------|-----------|
| SCN-1 | Competitor promotion, Karnataka beverages (−22%) | decoy competitor event in another region/category; national cricket season (opposite direction) |
| SCN-2 | Transport strike at DC-HYD-01, 8 SKUs (stockouts) | internal promotion during the strike (opposite direction); rain forecast after onset; routine maintenance |
| SCN-3 | Ganeshotsav festival, Maharashtra (+22…45%) | overlapping internal promotion (multi-explanation); festival outside monitored regions |
| SCN-4 | Product quality incident, Tamil Nadu curd (−18% for 30 days) | competitor BOGO starting 10 days *after* onset |
| SCN-5 | Unexplained dip, Delhi NCR toothpaste | unrelated local event the day before → must return insufficient evidence |
| SCN-6 | DC waterlogging + extreme rainfall, Maharashtra | two plausible overlapping explanations |

Ground truth (`backend/synthetic_data/output/ground_truth.json`) is read only by the evaluator.

### Latest evaluation (`.\run.ps1 -Evaluate`, deterministic mode)

| Metric | Value |
|---|---|
| Detection recall (16 GT windows) | 1.00 |
| Detection precision | 0.55 (13 extra, mostly LOW-severity anomalies) |
| False-positive rate (series-days) | 0.0008 |
| Retrieval MRR / Recall@3 | 1.00 / 1.00 (Precision@3 0.40 — most scenarios have 1 relevant event) |
| Top-hypothesis accuracy | 100% (16/16) incl. SCN-5 insufficient evidence |
| Evidence grounding / non-causal wording | 100% / 100% |
| Extra (false-positive) anomalies labelled INSUFFICIENT/WEAK | 100% |
| Investigation latency | ~51 ms mean (deterministic) |

**These numbers show engineering feasibility on synthetic data that the team designed. They are
not evidence of real-world causal accuracy.**

## Architecture

```
backend/
  app/            FastAPI app, env config (pydantic-settings)
  api/            datasets · analytics · anomalies · events · investigations · settings
  services/       ingestion · demand_analytics · anomaly_detection · event_matching ·
                  statistical_analysis · evidence_builder · hypothesis_generator ·
                  llm_provider · investigation_service · settings_service
  models/         SQLAlchemy 2.0 (relational, graph-ready traceability)
  database/       session + Alembic migrations
  config/         relevance.yaml — heuristic weights & category→mechanism map
  synthetic_data/ deterministic generator + scenarios
  evaluation/     P/R/F1/FPR, MRR/P@K/R@K, grounding, latency
  tests/          pytest (unit, scenario, API integration)
frontend/         Next.js 14 · TypeScript · Tailwind · Radix · ECharts · TanStack Query/Table · cmdk
```

**Database:** SQLite by default (`backend/data/demand_intel.db`); set `DATABASE_URL` for PostgreSQL
(install a driver such as `psycopg[binary]`). Tables: products, regions, demand_records,
inventory_records, promotions, operational_events, external_events, dataset_imports, anomalies,
investigations, candidate_drivers, evidence_records, hypotheses, hypothesis_evidence,
analyst_feedback, app_settings.

**Key API endpoints** (`/api/v1`, envelope `{data, meta, error}`): `POST /datasets/{type}/preview|import`,
`POST /datasets/load-synthetic`, `GET /analytics/overview|timeseries|regional`, `GET /anomalies`,
`POST /anomalies/detect`, `GET /events`, `POST /investigations`, `GET /investigations/{id}`,
`GET /investigations/{id}/stream` (SSE), `POST /hypotheses/{id}/feedback`, `GET|PUT /settings/...`.

## Analytical design and its limits

* **Three quantities are kept distinct:** `forecast_qty` (planned), `recorded_sales_qty` (observed,
  bounded by inventory), `estimated_unconstrained_demand` (only on stockout days, always labelled as
  an estimate). The CSV column `actual_sales_quantity` maps to `recorded_sales_qty`.
* **Detection:** robust z-score of the forecast residual against a *lagged, frozen* reference
  (90-day window ending 28 days earlier), re-estimated in a second pass with flagged days masked so
  sustained shifts are not absorbed into the baseline; plus two-sided CUSUM for persistent moderate
  shifts. Thresholds are configurable in Settings.
* **Event relevance** = weighted sum of temporal, geographic, product, operational and magnitude
  components (`config/relevance.yaml`). Every component score and reason is stored and shown. It is a
  ranking heuristic, **not** a probability.
* **Statistics are exploratory:** Welch comparisons of residual windows, difference-in-differences
  against other regions and same-category SKUs, inventory coverage and Spearman/lagged correlations
  (only with n ≥ 14), historical consistency. Each result records method, sample sizes, assumptions
  and caveats; p-values are descriptive.
* **Hypotheses** cite evidence IDs that are verified before persistence. Strength (STRONG / MODERATE
  / WEAK / INSUFFICIENT) comes from heuristic rules, not calibrated probabilities. Statistics cannot
  rescue a candidate whose mechanism or direction is contradicted.
* Only events present in uploaded datasets are screened. Live external event monitoring is not
  implemented.

## Known limitations of this MVP

* No authentication, multi-tenancy or billing.
* LLM mode is implemented and tested with a fake provider, but no live Claude call has been
  exercised in this environment (no API key was configured).
* PostgreSQL is supported through `DATABASE_URL` but was only exercised on SQLite here.
* Detection precision on the synthetic data is moderate (0.55); extra anomalies are mostly
  low-severity promotion-lift deviations, which the investigation engine labels as unsupported.
* The PRD's forecast blue (#58A6FF) and recorded-sales cyan (#39C5CF) sit close together for
  normal-vision readers (ΔE 12.7). They are kept per the design spec and told apart by line style
  (dashed vs solid), legend and tooltip labels.
