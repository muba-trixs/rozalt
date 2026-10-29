"""Scenario-level tests of the investigation engine (deterministic mode) and evidence validation."""
import datetime as dt

import pytest

from backend import models as M
from backend.services.hypothesis_generator import CAUSAL_PATTERN, HypothesisOut, HypothesisReport, validate_report
from backend.services.investigation_service import create_investigation, run_investigation
from backend.services.llm_provider import LLMResult
from backend.synthetic_data.scenarios import SCENARIOS


def _find_anomaly(db, sku, region, start, end, direction):
    for a in db.query(M.Anomaly).filter_by(sku_id=sku, region_id=region, direction=direction):
        if a.start_date <= end and a.end_date >= start:
            return a
    return None


def _investigate(db, anomaly, provider=None, use_llm=False):
    inv = create_investigation(db, anomaly.anomaly_id)
    return run_investigation(db, inv.investigation_id, provider=provider, use_llm=use_llm or provider is not None)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["scenario_id"] for s in SCENARIOS])
def test_scenario_outcomes(loaded_db, scenario):
    db = loaded_db
    a, b = scenario["window"]
    for sku in scenario["affected_skus"]:
        anomaly = _find_anomaly(db, sku, scenario["region"], a, b, scenario["direction"])
        assert anomaly, f"{scenario['scenario_id']}: {sku} not detected"
        inv = _investigate(db, anomaly)
        assert inv.status == "COMPLETED", inv.error
        assert inv.analysis_mode == "deterministic"
        assert all(s["status"] == "completed" for s in inv.stage_log)
        top = inv.hypotheses[0]
        if scenario["expected_outcome"] == "insufficient_evidence":
            assert top.evidence_strength == "INSUFFICIENT"
            assert inv.summary == "Insufficient evidence to identify a likely driver."
        else:
            acceptable = {d["driver_type"] for d in scenario["acceptable_drivers"]}
            assert top.driver_type in acceptable, f"{sku}: got {top.driver_type}"
            assert top.evidence_strength in ("STRONG", "MODERATE")
        # Every hypothesis link resolves to persisted evidence of this investigation
        ev_ids = {e.evidence_id for e in inv.evidence}
        for h in inv.hypotheses:
            for link in h.links:
                assert link.evidence_id in ev_ids
            assert not CAUSAL_PATTERN.search(h.explanation)


def test_ground_truth_event_ranked_first(loaded_db):
    db = loaded_db
    for sc in SCENARIOS:
        if not sc["primary_event_ids"]:
            continue
        sku = sc["affected_skus"][0]
        anomaly = _find_anomaly(db, sku, sc["region"], *sc["window"], sc["direction"])
        inv = _investigate(db, anomaly)
        top_ids = {c.source_id for c in inv.candidates[:2]}
        assert top_ids & set(sc["primary_event_ids"]), f"{sc['scenario_id']}: top candidates {top_ids}"


def test_supply_vs_demand_distinction(loaded_db):
    """Strike scenario: stockouts must be surfaced and recorded sales flagged as understating demand."""
    db = loaded_db
    sc = next(s for s in SCENARIOS if s["scenario_id"] == "SCN-2")
    anomaly = _find_anomaly(db, "SKU-102", sc["region"], *sc["window"], "NEGATIVE")
    inv = _investigate(db, anomaly)
    titles = [e.title for e in inv.evidence]
    assert "Stockouts and reduced availability" in titles
    assert "Recorded sales understate demand on stockout days" in titles
    assert any("stockout" in lim for lim in inv.limitations)


def test_confounder_after_onset_is_contradicted(loaded_db):
    """SCN-4: the competitor BOGO starting 10 days after onset must carry contradicting evidence."""
    db = loaded_db
    sc = next(s for s in SCENARIOS if s["scenario_id"] == "SCN-4")
    anomaly = _find_anomaly(db, "SKU-401", sc["region"], *sc["window"], "NEGATIVE")
    inv = _investigate(db, anomaly)
    contra = [e for e in inv.evidence if e.source_id == "EXT-2032" and e.polarity == "contradicting"]
    assert contra
    assert inv.hypotheses[0].driver_type == "product_quality"


def _evidence_stub(db):
    sc = SCENARIOS[0]
    anomaly = _find_anomaly(db, sc["affected_skus"][0], sc["region"], *sc["window"], sc["direction"])
    return anomaly


class FakeProvider:
    name, model = "fake", "fake-model"

    def __init__(self, reports):
        self.reports, self.calls = list(reports), 0

    def generate(self, package, feedback=None):
        self.calls += 1
        self.package = package
        rep = self.reports.pop(0)
        return LLMResult(rep(package) if callable(rep) else rep, [], 12.0, "fake-model")


def _llm_report(package, eid=None, text="The decline coincided with a competitor promotion in the region."):
    ev = eid or next(e["evidence_id"] for e in package["evidence"] if e["targets"])
    return HypothesisReport(
        investigation_summary="Evidence is consistent with competitor activity.",
        hypotheses=[HypothesisOut(title="Competitor activity", driver_type="competitor_activity",
                                  evidence_strength="MODERATE", claim_type="hypothesis", explanation=text,
                                  supporting_evidence_ids=[ev], contradicting_evidence_ids=[],
                                  recommended_actions=["Check competitor pricing"])],
        limitations=["Underlying demand is not observed."],
    )


def test_llm_valid_output_is_used(loaded_db):
    anomaly = _evidence_stub(loaded_db)
    prov = FakeProvider([_llm_report])
    inv = _investigate(loaded_db, anomaly, provider=prov)
    assert inv.analysis_mode == "llm" and prov.calls == 1
    assert inv.hypotheses[0].generated_by == "llm"
    # The model only receives structured evidence, with quantity definitions kept distinct
    assert set(prov.package["quantities"]) == {"forecast_qty", "recorded_sales_qty", "underlying_demand"}


def test_llm_fabricated_evidence_rejected_then_fallback(loaded_db):
    anomaly = _evidence_stub(loaded_db)
    bad = lambda p: _llm_report(p, eid="INV-9999-EV-99")  # noqa: E731
    prov = FakeProvider([bad, bad])
    inv = _investigate(loaded_db, anomaly, provider=prov)
    assert prov.calls == 2  # one retry with validation feedback
    assert inv.analysis_mode == "deterministic"
    assert any("unknown evidence ID INV-9999-EV-99" in n for n in inv.llm_notes)
    assert inv.status == "COMPLETED"


def test_llm_causal_language_rejected_then_corrected(loaded_db):
    anomaly = _evidence_stub(loaded_db)
    causal = lambda p: _llm_report(p, text="The competitor promotion caused the decline.")  # noqa: E731
    prov = FakeProvider([causal, _llm_report])
    inv = _investigate(loaded_db, anomaly, provider=prov)
    assert inv.analysis_mode == "llm" and prov.calls == 2
    assert any("causal-certainty" in n for n in inv.llm_notes)


def test_validator_rules():
    from backend.services.evidence_builder import Evidence

    ev = [Evidence("X-EV-01", "fact", "t", "d", targets={"a:b": {"role": "supporting", "weight": 0}})]
    good = HypothesisReport(investigation_summary="ok", limitations=[], hypotheses=[HypothesisOut(
        title="t", driver_type="weather", evidence_strength="WEAK", claim_type="hypothesis",
        explanation="Associated with rainfall.", supporting_evidence_ids=["X-EV-01"],
        contradicting_evidence_ids=[], recommended_actions=[])])
    assert validate_report(good, ev, {"weather"}) == []
    bad = good.model_copy(deep=True)
    bad.hypotheses[0].claim_type = "fact"
    bad.hypotheses[0].driver_type = "aliens"
    bad.hypotheses[0].explanation = "Rain led to a 90% probability decline"
    problems = " | ".join(validate_report(bad, ev, {"weather"}))
    assert "verified fact" in problems and "aliens" in problems and "causal" in problems


def test_failed_stage_is_reported_not_hidden(db):
    """An investigation on a series with no demand rows must fail at the retrieval stage."""
    db.add_all([M.Region(region_id="X"), M.Product(sku_id="S", product_name="P", category="C")])
    db.add(M.Anomaly(anomaly_id="ANM-1", sku_id="S", region_id="X", start_date=dt.date(2026, 1, 1),
                     end_date=dt.date(2026, 1, 3), peak_date=dt.date(2026, 1, 2), duration_days=3, forecast_qty=1,
                     recorded_sales_qty=1, variance_pct=-20, peak_robust_z=-4, direction="NEGATIVE",
                     severity="MEDIUM", detection_method="forecast_residual"))
    db.commit()
    inv = create_investigation(db, "ANM-1")
    inv = run_investigation(db, inv.investigation_id, use_llm=False)
    assert inv.status == "FAILED"
    stages = {s["key"]: s["status"] for s in inv.stage_log}
    assert stages["retrieve"] == "failed" and stages["report"] == "pending"
