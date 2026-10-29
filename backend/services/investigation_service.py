"""End-to-end investigation pipeline (stages 1–9) with real, persisted stage progress."""
from __future__ import annotations

import datetime as dt
import logging
import time
import traceback
from collections.abc import Callable

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models as M
from backend.app.config import Settings, get_settings
from backend.services import statistical_analysis as sa
from backend.services.demand_analytics import add_series_metrics, load_demand
from backend.services.event_matching import rank_events
from backend.services.evidence_builder import build_evidence
from backend.services.hypothesis_generator import (
    HypothesisReport,
    deterministic_report,
    validate_report,
)
from backend.services.llm_provider import LLMProvider, get_provider
from backend.services.settings_service import get_detection_config, get_relevance_config

logger = logging.getLogger("demand_intel.investigation")

STAGES = [
    ("retrieve", "Retrieving demand history"),
    ("context", "Characterising the deviation"),
    ("discover", "Identifying relevant events"),
    ("rank", "Ranking candidate events"),
    ("statistics", "Evaluating statistical relationships"),
    ("evidence", "Constructing evidence"),
    ("reasoning", "Generating hypotheses"),
    ("validate", "Validating evidence references"),
    ("report", "Preparing investigation report"),
]
CONTEXT_DAYS = 90
MAX_CANDIDATES = 8


class InvestigationError(Exception):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def create_investigation(db: Session, anomaly_id: str) -> M.Investigation:
    anomaly = db.get(M.Anomaly, anomaly_id)
    if anomaly is None:
        raise InvestigationError(f"Anomaly {anomaly_id} not found")
    last = db.scalar(select(func.max(M.Investigation.investigation_id)))
    num = int(last.split("-")[1]) + 1 if last else 1001
    inv = M.Investigation(
        investigation_id=f"INV-{num}", anomaly_id=anomaly_id, status="RUNNING",
        stage_log=[{"key": k, "label": label, "status": "pending"} for k, label in STAGES],
    )
    anomaly.status = "INVESTIGATING"
    db.add(inv)
    db.commit()
    return inv


class _Runner:
    def __init__(self, db: Session, inv: M.Investigation):
        self.db, self.inv = db, inv
        self.log = [dict(s) for s in inv.stage_log]
        self.timings: dict[str, float] = {}

    def stage(self, key: str, fn: Callable[[], object], detail: Callable[[object], str] | None = None):
        entry = next(s for s in self.log if s["key"] == key)
        entry.update(status="running", started_at=_now().isoformat())
        self._flush()
        t0 = time.perf_counter()
        try:
            out = fn()
        except Exception as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                         duration_ms=round((time.perf_counter() - t0) * 1000, 1))
            self._flush()
            raise
        ms = round((time.perf_counter() - t0) * 1000, 1)
        entry.update(status="completed", duration_ms=ms)
        if detail:
            entry["detail"] = detail(out)
        self.timings[key] = ms
        self._flush()
        return out

    def _flush(self):
        self.inv.stage_log = [dict(s) for s in self.log]
        self.db.commit()


def _evidence_package(anomaly, product, candidates, evidence, stats, det_report: HypothesisReport) -> dict:
    return {
        "quantities": {
            "forecast_qty": "planned quantity from the demand plan",
            "recorded_sales_qty": "observed sales; bounded by available inventory",
            "underlying_demand": "NOT observed; only estimated on stockout days",
        },
        "anomaly": {
            "anomaly_id": anomaly.anomaly_id, "sku_id": anomaly.sku_id, "product_name": product.product_name,
            "category": product.category, "region": anomaly.region_id, "start_date": anomaly.start_date,
            "end_date": anomaly.end_date, "direction": anomaly.direction,
            "variance_pct_recorded_sales_vs_forecast": anomaly.variance_pct, "severity": anomaly.severity,
            "detection_method": anomaly.detection_method,
        },
        "candidate_events": [
            {"key": c.key, "event_id": c.source_id, "driver_type": c.driver_type, "category": c.category,
             "title": c.title, "region": c.region, "start": c.start, "end": c.end, "mechanism": c.mechanism,
             "heuristic_relevance": c.score, "relevance_components": c.components, "relevance_reasons": c.reasons}
            for c in candidates
        ],
        "evidence": [
            {"evidence_id": e.evidence_id, "kind": e.kind, "title": e.title, "description": e.description,
             "targets": e.targets}
            for e in evidence
        ],
        "statistics_summary": {
            "anomaly_window": stats["context"]["window_comparison"],
            "peer_regions": {k: stats["peer_regions"].get(k) for k in
                             ("pattern", "did_estimate_pct_points", "n_comparison_series")},
            "peer_category": {k: stats["peer_category"].get(k) for k in
                              ("pattern", "did_estimate_pct_points", "n_comparison_series")},
            "inventory": {k: stats["inventory"].get(k) for k in
                          ("stockout_days_in_window", "coverage_change_pct", "supply_constraint_observed",
                           "estimated_unserved_units")},
        },
        "deterministic_baseline_ranking": [
            {"driver_type": h.driver_type, "evidence_strength": h.evidence_strength}
            for h in det_report.hypotheses
        ],
        "required_limitations": det_report.limitations,
    }


def run_investigation(db: Session, investigation_id: str, settings: Settings | None = None,
                      provider: LLMProvider | None = None, use_llm: bool = True) -> M.Investigation:
    settings = settings or get_settings()
    inv = db.get(M.Investigation, investigation_id)
    anomaly = db.get(M.Anomaly, inv.anomaly_id)
    product = db.get(M.Product, anomaly.sku_id)
    rel_cfg = get_relevance_config(db)
    det_cfg = get_detection_config(db)
    r = _Runner(db, inv)
    t_start = time.perf_counter()
    try:
        lo = anomaly.start_date - dt.timedelta(days=CONTEXT_DAYS)
        hi = anomaly.end_date + dt.timedelta(days=21)

        def retrieve():
            focal = load_demand(db, anomaly.sku_id, anomaly.region_id, lo, hi, with_inventory=True)
            if focal.empty:
                raise InvestigationError("No demand history for this SKU/region")
            same_sku = load_demand(db, sku_id=anomaly.sku_id, start=lo, end=hi)
            region_df = load_demand(db, region=anomaly.region_id, start=lo, end=hi)
            cat_skus = set(db.scalars(select(M.Product.sku_id).where(M.Product.category == product.category)))
            return add_series_metrics(focal), same_sku, region_df[region_df.sku_id.isin(cat_skus)]

        focal, same_sku, same_cat = r.stage("retrieve", retrieve,
                                            lambda o: f"{len(o[0])} days focal, {len(o[1]) + len(o[2])} comparison rows")

        context = r.stage("context", lambda: sa.anomaly_context(focal, anomaly),
                          lambda c: f"{c['variance_pct']:+.1f}% over {c['window_days']} days")

        events = r.stage("discover", lambda: rank_events(db, anomaly, rel_cfg),
                         lambda e: f"{len(e)} events in window")

        def rank():
            th = rel_cfg["window"]["min_candidate_score"]
            return [e for e in events if e.score >= th][:MAX_CANDIDATES]

        candidates = r.stage("rank", rank, lambda c: f"{len(c)} candidates above threshold")

        def statistics():
            peers_r = same_sku[same_sku.region != anomaly.region_id].assign(group=lambda d: d.region)
            peers_c = same_cat[same_cat.sku_id != anomaly.sku_id].assign(group=lambda d: d.sku_id)
            ew, hist = {}, {}
            for c in candidates:
                if c.start <= anomaly.end_date:
                    ew[c.key] = sa.event_window(focal, anomaly, c)
                prior = _prior_events(db, c, anomaly)
                hist[c.key] = sa.historical_consistency(focal_full, anomaly, c, prior, det_cfg["min_window_variance"])
            return {
                "context": context,
                "event_windows": ew,
                "history": hist,
                "peer_regions": sa.peer_comparison(peers_r, focal, anomaly, f"{anomaly.sku_id} in other regions"),
                "peer_category": sa.peer_comparison(peers_c, focal, anomaly,
                                                    f"other {product.category} SKUs in {anomaly.region_id}"),
                "inventory": sa.inventory_analysis(focal, anomaly),
            }

        focal_full = load_demand(db, anomaly.sku_id, anomaly.region_id)
        stats = r.stage("statistics", statistics,
                        lambda s: f"{len(s['event_windows'])} event windows, peers: {s['peer_regions'].get('pattern')}")

        evidence = r.stage("evidence", lambda: build_evidence(inv.investigation_id, anomaly, product, candidates,
                                                              stats, det_cfg["min_window_variance"],
                                                              int(rel_cfg["window"].get("onset_tolerance_days", 1))),
                           lambda e: f"{len(e)} evidence items")

        allowed = {c.driver_type for c in candidates} | {"inventory_constraint"}
        notes: list[str] = []

        def reasoning():
            det, scores = deterministic_report(anomaly, product, candidates, evidence, stats, rel_cfg, len(events))
            prov = provider if provider is not None else (get_provider(settings) if use_llm else None)
            if prov is None:
                notes.append("No LLM configured — deterministic rule-based synthesis used.")
                return det, scores, "deterministic", None
            package = _evidence_package(anomaly, product, candidates, evidence, stats, det)
            feedback = None
            for attempt in (1, 2):
                res = prov.generate(package, feedback)
                notes.extend(res.notes)
                r.timings[f"llm_attempt_{attempt}_ms"] = round(res.latency_ms, 1)
                if res.report is None:
                    break
                problems = validate_report(res.report, evidence, allowed)
                if not problems:
                    return res.report, scores, "llm", res.served_model or prov.model
                notes.append(f"LLM attempt {attempt} rejected: " + "; ".join(problems[:5]))
                feedback = problems
            notes.append("Fell back to deterministic synthesis after LLM output could not be validated.")
            return det, scores, "deterministic", None

        report, scores, mode, model = r.stage("reasoning", reasoning,
                                              lambda o: f"{o[2]} mode, {len(o[0].hypotheses)} hypotheses")

        def validate():
            problems = validate_report(report, evidence, allowed)
            if problems:
                raise InvestigationError("Report failed validation: " + "; ".join(problems))
            return len(report.hypotheses)

        r.stage("validate", validate, lambda n: f"{n} hypotheses, all evidence IDs verified")

        def persist():
            _persist(db, inv, events, candidates, evidence, report, scores, mode, model, stats, notes)
            return True

        r.stage("report", persist, lambda _: "Investigation saved")
        inv.status = "COMPLETED"
        anomaly.status = "INVESTIGATED"
    except Exception as exc:
        logger.error("Investigation %s failed: %s", investigation_id, traceback.format_exc())
        db.rollback()
        inv = db.get(M.Investigation, investigation_id)
        inv.stage_log = r.log
        inv.status = "FAILED"
        inv.error = f"{type(exc).__name__}: {exc}"
        anomaly = db.get(M.Anomaly, inv.anomaly_id)
        anomaly.status = "NEW" if not any(i.status == "COMPLETED" for i in anomaly.investigations) else "INVESTIGATED"
    r.timings["total_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
    inv.timings = r.timings
    inv.completed_at = _now()
    db.commit()
    return inv


def _prior_events(db: Session, c, anomaly) -> list[dict]:
    cutoff = anomaly.start_date - dt.timedelta(days=30)
    if c.source_table == "external_events":
        rows = db.scalars(select(M.ExternalEvent).where(
            M.ExternalEvent.event_category == c.category, M.ExternalEvent.region_id == c.region,
            M.ExternalEvent.event_date < cutoff, M.ExternalEvent.event_id != c.source_id)).all()
        return [{"id": e.event_id, "start": e.event_date.isoformat()} for e in rows]
    if c.source_table == "operational_events":
        rows = db.scalars(select(M.OperationalEvent).where(
            M.OperationalEvent.event_type == c.category, M.OperationalEvent.region_id == c.region,
            M.OperationalEvent.date < cutoff, M.OperationalEvent.event_id != c.source_id)).all()
        return [{"id": e.event_id, "start": e.date.isoformat()} for e in rows]
    rows = db.scalars(select(M.Promotion).where(
        M.Promotion.sku_id == anomaly.sku_id, M.Promotion.region_id == anomaly.region_id,
        M.Promotion.start_date < cutoff)).all()
    return [{"id": f"PROMO-{p.id}", "start": p.start_date.isoformat()} for p in rows]


def _persist(db, inv, events, candidates, evidence, report: HypothesisReport, scores, mode, model, stats, notes):
    cand_keys = {c.key for c in candidates}
    driver_lookup = {c.key: c.driver_type for c in events}
    for rank, e in enumerate(events[:25], 1):
        db.add(M.CandidateDriver(
            investigation_id=inv.investigation_id, rank=rank, source_table=e.source_table, source_id=e.source_id,
            driver_type=e.driver_type, title=e.title, event_date=e.start, event_end_date=e.end, region_id=e.region,
            relevance_score=e.score, component_scores=e.components,
            reasons={**e.reasons, "above_threshold": e.key in cand_keys, "category": e.category,
                     "mechanism": e.mechanism, "description": e.description, "source": e.source,
                     "source_url": e.source_url, "related_skus": e.related_skus,
                     "related_category": e.related_category, "severity": e.severity},
        ))
    for ev in evidence:
        d = ev.to_dict(driver_lookup)
        db.add(M.EvidenceRecord(investigation_id=inv.investigation_id, **d))
    db.flush()
    for rank, h in enumerate(report.hypotheses, 1):
        row = M.Hypothesis(
            investigation_id=inv.investigation_id, rank=rank, title=h.title, driver_type=h.driver_type,
            evidence_strength=h.evidence_strength, claim_type=h.claim_type, explanation=h.explanation,
            recommended_actions=h.recommended_actions, score=scores.get(h.driver_type), generated_by=mode,
        )
        db.add(row)
        db.flush()
        seen = set()
        for eid in h.supporting_evidence_ids:
            if eid not in seen:
                db.add(M.HypothesisEvidence(hypothesis_id=row.id, evidence_id=eid, role="supporting"))
                seen.add(eid)
        for eid in h.contradicting_evidence_ids:
            if eid not in seen:
                db.add(M.HypothesisEvidence(hypothesis_id=row.id, evidence_id=eid, role="contradicting"))
                seen.add(eid)
    inv.summary = report.investigation_summary
    inv.limitations = report.limitations
    inv.analysis_mode = mode
    inv.model = model
    inv.llm_notes = notes
    inv.statistics = _jsonable(stats)


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return o


def serialize_investigation(db: Session, inv: M.Investigation) -> dict:
    a = inv.anomaly
    product = db.get(M.Product, a.sku_id)
    return {
        "investigation_id": inv.investigation_id,
        "status": inv.status,
        "analysis_mode": inv.analysis_mode,
        "model": inv.model,
        "summary": inv.summary,
        "limitations": inv.limitations or [],
        "llm_notes": inv.llm_notes or [],
        "error": inv.error,
        "stage_log": inv.stage_log or [],
        "timings": inv.timings or {},
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "completed_at": inv.completed_at.isoformat() if inv.completed_at else None,
        "anomaly": serialize_anomaly(a, product),
        "statistics": inv.statistics or {},
        "candidates": [
            {"rank": c.rank, "source_table": c.source_table, "source_id": c.source_id, "driver_type": c.driver_type,
             "title": c.title, "event_date": c.event_date.isoformat(),
             "event_end_date": c.event_end_date.isoformat() if c.event_end_date else None, "region": c.region_id,
             "relevance_score": c.relevance_score, "components": c.component_scores, "reasons": c.reasons}
            for c in inv.candidates
        ],
        "evidence": [
            {"evidence_id": e.evidence_id, "kind": e.kind, "polarity": e.polarity, "driver_types": e.driver_types,
             "source_table": e.source_table, "source_id": e.source_id, "title": e.title,
             "description": e.description, "payload": e.payload}
            for e in inv.evidence
        ],
        "hypotheses": [
            {"id": h.id, "rank": h.rank, "title": h.title, "driver_type": h.driver_type,
             "evidence_strength": h.evidence_strength, "claim_type": h.claim_type, "explanation": h.explanation,
             "recommended_actions": h.recommended_actions, "score": h.score, "generated_by": h.generated_by,
             "supporting_evidence_ids": [l.evidence_id for l in h.links if l.role == "supporting"],
             "contradicting_evidence_ids": [l.evidence_id for l in h.links if l.role == "contradicting"],
             "feedback": [{"id": f.id, "verdict": f.verdict, "note": f.note,
                           "created_at": f.created_at.isoformat() if f.created_at else None} for f in h.feedback]}
            for h in inv.hypotheses
        ],
    }


def serialize_anomaly(a: M.Anomaly, product: M.Product | None) -> dict:
    return {
        "anomaly_id": a.anomaly_id, "sku_id": a.sku_id, "product_name": product.product_name if product else None,
        "category": product.category if product else None, "region": a.region_id,
        "start_date": a.start_date.isoformat(), "end_date": a.end_date.isoformat(),
        "peak_date": a.peak_date.isoformat(), "duration_days": a.duration_days, "forecast_qty": a.forecast_qty,
        "recorded_sales_qty": a.recorded_sales_qty, "variance_pct": a.variance_pct,
        "peak_robust_z": a.peak_robust_z, "direction": a.direction, "severity": a.severity,
        "detection_method": a.detection_method, "status": a.status, "details": a.details,
    }
