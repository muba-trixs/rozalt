"""Synthetic-scenario evaluation.

    python -m backend.evaluation.evaluate [--llm]

Loads the deterministic synthetic dataset into a throw-away SQLite database, runs detection and an
investigation for every detected anomaly, and scores the results against the hidden ground truth
(``ground_truth.json`` — read only here, never by the engine).

These numbers demonstrate engineering feasibility on synthetic data. They are NOT estimates of
real-world causal accuracy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import tempfile
import time
from pathlib import Path

from sqlalchemy.orm import sessionmaker

import backend.models as M
from backend.database.session import Base, make_engine
from backend.services.hypothesis_generator import CAUSAL_PATTERN
from backend.services.investigation_service import create_investigation, run_investigation
from backend.services.synthetic_loader import load_synthetic

K = 3
REPORT_PATH = Path(__file__).resolve().parent / "latest_report.json"


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _gt_windows(gt: dict) -> list[dict]:
    out = []
    for sc in gt["scenarios"]:
        for sku in sc["affected_skus"]:
            out.append({"scenario": sc, "sku_id": sku, "region": sc["region"], "start": _d(sc["start"]),
                        "end": _d(sc["end"]), "direction": sc["direction"]})
    return out


def _overlaps(a: M.Anomaly, w: dict) -> bool:
    return (a.sku_id == w["sku_id"] and a.region_id == w["region"] and a.direction == w["direction"]
            and a.start_date <= w["end"] and a.end_date >= w["start"])


def evaluate(use_llm: bool = False) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="di-eval-"))
    engine = make_engine(f"sqlite:///{(tmp / 'eval.db').as_posix()}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    t0 = time.perf_counter()
    load = load_synthetic(db)
    load_s = time.perf_counter() - t0
    from backend.app.config import SYNTHETIC_OUTPUT_DIR

    gt = json.loads((SYNTHETIC_OUTPUT_DIR / "ground_truth.json").read_text(encoding="utf-8"))
    windows = _gt_windows(gt)
    anomalies = db.query(M.Anomaly).order_by(M.Anomaly.start_date).all()

    # ---------------- Detection ----------------
    matched_gt, tp_anoms, fp_anoms = set(), [], []
    for a in anomalies:
        hits = [i for i, w in enumerate(windows) if _overlaps(a, w)]
        if hits:
            tp_anoms.append((a, windows[hits[0]]))
            matched_gt.update(hits)
        else:
            fp_anoms.append(a)
    tp, fp, fn = len(matched_gt), len(fp_anoms), len(windows) - len(matched_gt)
    precision = len(tp_anoms) / max(len(anomalies), 1)
    recall = tp / max(len(windows), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    n_series = db.query(M.DemandRecord.sku_id, M.DemandRecord.region_id).distinct().count()
    n_days = db.query(M.DemandRecord).count()
    gt_days = sum((w["end"] - w["start"]).days + 1 for w in windows)
    fp_days = sum(a.duration_days for a in fp_anoms)
    fpr = fp_days / max(n_days - gt_days, 1)

    # ---------------- Investigations ----------------
    rr, p_at_k, r_at_k = [], [], []
    top_correct, insuff_ok, grounded, causal_free, temporal_ok, geo_ok = [], [], [], [], [], []
    confounder_handled, fp_uncertain = [], []
    latency, stage_ms = [], {}
    per_scenario: dict[str, list] = {}

    for a in anomalies:
        inv = create_investigation(db, a.anomaly_id)
        inv = run_investigation(db, inv.investigation_id, use_llm=use_llm)
        latency.append(inv.timings.get("total_ms", 0.0))
        for s in inv.stage_log:
            if s.get("duration_ms") is not None:
                stage_ms.setdefault(s["key"], []).append(s["duration_ms"])
        ev_ids = {e.evidence_id for e in inv.evidence}
        for h in inv.hypotheses:
            grounded.append(all(l.evidence_id in ev_ids for l in h.links))
            causal_free.append(CAUSAL_PATTERN.search(h.explanation) is None)

        match = next((w for (x, w) in tp_anoms if x.anomaly_id == a.anomaly_id), None)
        top = inv.hypotheses[0] if inv.hypotheses else None
        if match is None:
            fp_uncertain.append(top is not None and top.evidence_strength in ("INSUFFICIENT", "WEAK"))
            continue

        sc = match["scenario"]
        relevant = {d["event_id"] for d in sc["acceptable_drivers"] if d.get("event_id")}
        ranked = [c.source_id for c in inv.candidates if (c.reasons or {}).get("above_threshold")]
        if relevant:
            rank = next((i + 1 for i, s in enumerate(ranked) if s in relevant), None)
            rr.append(1.0 / rank if rank else 0.0)
            top_k = ranked[:K]
            p_at_k.append(len([s for s in top_k if s in relevant]) / K)
            r_at_k.append(len([s for s in top_k if s in relevant]) / len(relevant))

        if sc["expected_outcome"] == "insufficient_evidence":
            ok = top is not None and top.evidence_strength == "INSUFFICIENT"
            insuff_ok.append(ok)
        else:
            acceptable = {d["driver_type"] for d in sc["acceptable_drivers"]}
            ok = top is not None and top.driver_type in acceptable and top.evidence_strength != "INSUFFICIENT"
            # temporal / geographic consistency of the top hypothesis' primary event
            cand = next((c for c in inv.candidates if c.driver_type == top.driver_type), None) if top else None
            if cand:
                temporal_ok.append(cand.event_date <= a.start_date + dt.timedelta(days=5))
                geo_ok.append(cand.region_id in (a.region_id, "National"))
        top_correct.append(ok)
        per_scenario.setdefault(sc["scenario_id"], []).append(
            {"anomaly_id": a.anomaly_id, "sku_id": a.sku_id, "top_driver": top.driver_type if top else None,
             "strength": top.evidence_strength if top else None, "correct": ok})

        # Confounders listed in ground truth must never be the top hypothesis' primary event
        confounder_ids = {"EXT-2032", "EXT-2011", "EXT-2002", "EXT-2041", "OPS-3002"}
        top_cand = next((c for c in inv.candidates if top and c.driver_type == top.driver_type), None)
        if any(c.source_id in confounder_ids for c in inv.candidates):
            confounder_handled.append(top_cand is None or top_cand.source_id not in confounder_ids)

    def mean(x):
        return round(statistics.fmean(x), 4) if x else None

    def pct(x):
        return round(100 * statistics.fmean([1.0 if v else 0.0 for v in x]), 1) if x else None

    lat_sorted = sorted(latency)
    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": "llm" if use_llm else "deterministic",
        "disclaimer": "Synthetic-data evaluation demonstrates engineering feasibility, not real-world causal accuracy.",
        "dataset": {"series": n_series, "days": n_days, "ground_truth_windows": len(windows),
                    "scenarios": len(gt["scenarios"]), "load_seconds": round(load_s, 2)},
        "detection": {
            "anomalies_detected": len(anomalies), "gt_windows_detected": tp, "missed": fn,
            "false_positive_anomalies": fp, "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "false_positive_rate_days": round(fpr, 5),
        },
        "retrieval": {"k": K, "mrr": mean(rr), "precision_at_k": mean(p_at_k), "recall_at_k": mean(r_at_k),
                      "n": len(rr)},
        "explanations": {
            "top_hypothesis_accuracy_pct": pct(top_correct),
            "insufficient_evidence_handled_pct": pct(insuff_ok),
            "evidence_grounding_pct": pct(grounded),
            "non_causal_language_pct": pct(causal_free),
            "temporal_consistency_pct": pct(temporal_ok),
            "geographic_consistency_pct": pct(geo_ok),
            "confounders_not_top_ranked_pct": pct(confounder_handled),
            "false_positives_flagged_uncertain_pct": pct(fp_uncertain),
            "per_scenario": per_scenario,
        },
        "latency_ms": {
            "investigation_mean": mean(latency),
            "investigation_p95": lat_sorted[int(0.95 * (len(lat_sorted) - 1))] if lat_sorted else None,
            "per_stage_mean": {k: mean(v) for k, v in stage_ms.items()},
        },
        "load": load,
    }
    db.close()
    engine.dispose()
    return report


def _print(r: dict) -> None:
    print(f"\nRozalt - synthetic evaluation ({r['mode']} mode)")
    print(r["disclaimer"])
    print("\nDETECTION")
    for k, v in r["detection"].items():
        print(f"  {k:32s} {v}")
    print(f"\nEVENT RETRIEVAL (K={r['retrieval']['k']})")
    for k in ("mrr", "precision_at_k", "recall_at_k", "n"):
        print(f"  {k:32s} {r['retrieval'][k]}")
    print("\nEXPLANATIONS")
    for k, v in r["explanations"].items():
        if k != "per_scenario":
            print(f"  {k:40s} {v}")
    for sid, rows in r["explanations"]["per_scenario"].items():
        ok = sum(1 for x in rows if x["correct"])
        print(f"    {sid}: {ok}/{len(rows)} correct - " + ", ".join(f"{x['sku_id']}->{x['top_driver']}({x['strength']})" for x in rows))
    print("\nLATENCY (ms)")
    print(f"  investigation mean {r['latency_ms']['investigation_mean']}  p95 {r['latency_ms']['investigation_p95']}")
    for k, v in r["latency_ms"]["per_stage_mean"].items():
        print(f"    {k:12s} {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use the configured LLM provider (requires ANTHROPIC_API_KEY)")
    args = ap.parse_args()
    rep = evaluate(use_llm=args.llm)
    REPORT_PATH.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    _print(rep)
    print(f"\nFull report: {REPORT_PATH}")
