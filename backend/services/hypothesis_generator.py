"""Module F — hypothesis generation and strict validation.

Two engines produce the same ``HypothesisReport`` schema:
  * deterministic — rule-based ranking of evidence (always available, fully reproducible)
  * llm           — Claude synthesises hypotheses from the structured evidence only

Every report, from either engine, passes ``validate_report``: cited evidence IDs must exist,
supporting/contradicting roles must be consistent with the evidence, and explanations must not
use causal-certainty language.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from backend.services.event_matching import CandidateEvent
from backend.services.evidence_builder import INVENTORY_KEY, Evidence

Strength = Literal["STRONG", "MODERATE", "WEAK", "INSUFFICIENT"]
ClaimType = Literal["fact", "association", "hypothesis", "assumption"]

CAUSAL_PATTERN = re.compile(
    r"\b(caused|causes|causing|cause of|proves?|proved|proven|definitively|certainly|undoubtedly|"
    r"due to|because of|resulted in|results in|led to|leads to|drove|driven by)\b",
    re.IGNORECASE,
)
INSUFFICIENT_SUMMARY = "Insufficient evidence to identify a likely driver."

DRIVER_TITLES = {
    "competitor_activity": "Competitor activity",
    "distribution_disruption": "Distribution disruption",
    "product_quality": "Product quality incident",
    "cultural_event": "Cultural / festival demand",
    "weather": "Weather disruption",
    "internal_promotion": "Internal promotion effect",
    "social_trend": "Social / consumer trend",
    "regulatory": "Regulatory change",
    "macroeconomic": "Macroeconomic shift",
    "operational_routine": "Routine operational activity",
    "inventory_constraint": "Unexplained supply constraint",
    "other": "Other recorded event",
    "none": "No supported driver",
}

ACTIONS = {
    "competitor_activity": ["Obtain competitor price and promotion tracking for the region",
                            "Compare retailer-level sell-out where the competitor offer was active",
                            "Review price-gap versus competitor during the window"],
    "distribution_disruption": ["Verify distributor fulfilment and dispatch records for the affected facility",
                                "Review retailer stockout and OOS reports for the window",
                                "Estimate unserved demand separately from recorded sales before re-forecasting"],
    "product_quality": ["Trace distribution of the affected batch to distributors and retailers",
                        "Review complaint volumes and themes against the sales timeline",
                        "Check returns / write-off data for the affected SKU"],
    "cultural_event": ["Confirm festival dates and regional scope for future forecast cycles",
                       "Check whether comparable SKUs in the region show the same uplift",
                       "Consider adding the event to the planning calendar"],
    "weather": ["Review footfall and logistics reports for the weather period",
                "Separate supply-side availability effects from demand effects"],
    "internal_promotion": ["Compare realised promotion lift with the planned lift in the forecast",
                           "Review promotion execution (display, pricing compliance) at retailers"],
    "inventory_constraint": ["Investigate replenishment and allocation records for the window",
                             "Check for unrecorded logistics or supplier issues"],
    "none": ["Check for unrecorded local events (retailer delistings, price changes, local disruptions)",
             "Verify POS / sell-in data completeness for the window",
             "Continue monitoring; re-investigate if the deviation persists"],
}


class HypothesisOut(BaseModel):
    title: str = Field(description="Short name of the hypothesised driver")
    driver_type: str = Field(description="One of the driver types present in the candidate events, or 'none'")
    evidence_strength: Strength
    claim_type: ClaimType = Field(description="Use 'hypothesis' for drivers; never 'fact' for a causal claim")
    explanation: str = Field(description="Evidence-grounded explanation using associative, non-causal language")
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    recommended_actions: list[str]


class HypothesisReport(BaseModel):
    investigation_summary: str
    hypotheses: list[HypothesisOut]
    limitations: list[str]


def _strength(score: float, cfg: dict, has_corroboration: bool, max_contra: float) -> Strength | None:
    t = cfg["hypothesis"]
    if score >= t["strong"] and has_corroboration and max_contra < 0.25:
        return "STRONG"
    if score >= t["moderate"]:
        return "MODERATE"
    if score >= t["weak"]:
        return "WEAK"
    return None


def deterministic_report(anomaly, product, candidates: list[CandidateEvent], evidence: list[Evidence],
                         stats: dict, cfg: dict, screened: int) -> tuple[HypothesisReport, dict[str, float]]:
    by_driver: dict[str, list[CandidateEvent]] = {}
    for c in candidates:
        by_driver.setdefault(c.driver_type, []).append(c)

    inv = stats.get("inventory", {})
    if inv.get("supply_constraint_observed") and "distribution_disruption" not in by_driver \
            and anomaly.direction == "NEGATIVE":
        by_driver["inventory_constraint"] = []

    def assess(keys: set[str], base: float):
        sup, con = {}, {}
        for item in evidence:
            for k, t in item.targets.items():
                if k in keys:
                    (sup if t["role"] == "supporting" else con)[item.evidence_id] = (item, t["weight"])
        sup_l, con_l = list(sup.values()), list(con.values())
        # Corroboration cannot rescue a candidate whose mechanism or direction is contradicted:
        # statistics only show that a deviation exists in the window, not that this event explains it.
        mechanism_blocked = any(i.kind == "context" and w >= 0.25 for i, w in con_l)
        bonus = 0.0 if mechanism_blocked else min(0.15, sum(w for _, w in sup_l))
        score = round(base + bonus - sum(w for _, w in con_l), 4)
        corroborated = any(i.kind == "statistical" and w > 0 for i, w in sup_l) or             any(i.source_table == "inventory_records" for i, _ in sup_l)
        return score, sup_l, con_l, corroborated

    scored = []
    for driver, evs in by_driver.items():
        # Each event is assessed on its own evidence; the best-supported event represents the driver.
        options = [(e, *assess({e.key}, e.score)) for e in evs] if evs else             [(None, *assess({INVENTORY_KEY}, 0.55))]
        primary, score, sup, con, corroborated = max(options, key=lambda o: o[1])
        others = [o for o in options if o[0] is not None and o[0] is not primary and o[1] >= cfg["hypothesis"]["weak"]]
        for o in others:  # other well-supported events of the same driver type add their supporting evidence
            sup += [x for x in o[2] if x[0].evidence_id not in {i.evidence_id for i, _ in sup}]
        strength = _strength(score, cfg, corroborated, max((w for _, w in con), default=0.0))
        if strength:
            scored.append((score, driver, [primary] if primary else [], sup, con, strength))
    scored.sort(key=lambda x: -x[0])

    hyps: list[HypothesisOut] = []
    scores: dict[str, float] = {}
    for score, driver, evs, sup, con, strength in scored:
        primary = max(evs, key=lambda e: e.score) if evs else None
        hyps.append(HypothesisOut(
            title=DRIVER_TITLES.get(driver, driver.replace("_", " ").title()),
            driver_type=driver, evidence_strength=strength, claim_type="hypothesis",
            explanation=_explain(anomaly, product, driver, primary, sup, con, stats),
            supporting_evidence_ids=[i.evidence_id for i, _ in sup],
            contradicting_evidence_ids=[i.evidence_id for i, _ in con],
            recommended_actions=ACTIONS.get(driver, ACTIONS["none"])[:3],
        ))
        scores[driver] = score

    limitations = build_limitations(anomaly, stats, screened, len(candidates))
    if not hyps:
        rejected = [f"{c.source_id} (relevance {c.score:.2f})" for c in candidates[:4]]
        expl = (f"{screened} recorded events were screened for the window; "
                + (f"the closest candidates ({', '.join(rejected)}) lacked a plausible mechanism, region match "
                   f"or timing alignment once contradicting evidence was weighed." if rejected else
                   "none met the minimum relevance threshold.")
                + " The deviation remains statistically unusual but unexplained by the available data.")
        hyps.append(HypothesisOut(
            title=DRIVER_TITLES["none"], driver_type="none", evidence_strength="INSUFFICIENT",
            claim_type="assumption", explanation=expl,
            supporting_evidence_ids=[evidence[0].evidence_id] if evidence else [],
            contradicting_evidence_ids=[], recommended_actions=ACTIONS["none"],
        ))
        summary = INSUFFICIENT_SUMMARY
    else:
        top = hyps[0]
        summary = (f"The strongest available evidence is consistent with {top.title.lower()} "
                   f"({top.evidence_strength.lower()} evidence)")
        if len(hyps) > 1:
            summary += f"; {len(hyps) - 1} alternative explanation(s) remain plausible and are ranked below"
        summary += ". Associations are not proof of cause."
    return HypothesisReport(investigation_summary=summary, hypotheses=hyps, limitations=limitations), scores


def _explain(anomaly, product, driver, primary, sup, con, stats) -> str:
    parts = []
    if primary:
        lag = (anomaly.start_date - primary.start).days
        when = (f"started {lag} day(s) before" if lag > 0 else
                "started on the same day as" if lag == 0 else f"started {-lag} day(s) after")
        parts.append(f"{primary.source_id} ({primary.title}) {when} the {anomaly.direction.lower()} deviation "
                     f"in {anomaly.region_id} (heuristic relevance {primary.score:.2f}).")
    else:
        parts.append("Stockouts and reduced inventory coverage overlap the deviation, but no recorded supply event "
                     "explains them.")
    stat_sup = [i for i, w in sup if i.kind == "statistical" and w > 0]
    if stat_sup:
        parts.append("The pattern is consistent with: " + "; ".join(_lc(i.title) for i in stat_sup[:3]) + ".")
    if any(i.source_table == "inventory_records" for i, _ in sup):
        parts.append("Inventory data show reduced availability, so recorded sales likely understate underlying demand.")
    if con:
        parts.append("Weighing against it: " + "; ".join(_lc(i.title) for i, _ in con[:3]) + ".")
    parts.append("This is an association-based hypothesis that requires verification.")
    return " ".join(parts)


def _lc(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


def build_limitations(anomaly, stats: dict, screened: int, n_candidates: int) -> list[str]:
    lim = ["Underlying consumer demand is not directly observed; analysis uses recorded sales versus forecast.",
           "Event relevance scores are heuristic rankings, not probabilities of causation.",
           "Statistical comparisons are exploratory and do not establish causality."]
    inv = stats.get("inventory", {})
    if inv.get("insufficient_data"):
        lim.append("No inventory data: supply-side explanations could not be assessed.")
    elif inv.get("stockout_days_in_window"):
        lim.append(f"{inv['stockout_days_in_window']} stockout day(s) in the window: recorded sales are bounded by "
                   f"availability and understate demand on those days.")
    if stats.get("context", {}).get("window_comparison", {}).get("insufficient_data"):
        lim.append("Insufficient pre-period history for a window comparison.")
    if stats.get("peer_regions", {}).get("insufficient_data"):
        lim.append("No comparison regions available for this SKU.")
    lim.append(f"Only events present in the uploaded datasets were screened ({screened} in the window); "
               f"unrecorded events cannot be detected.")
    return lim


def validate_report(report: HypothesisReport, evidence: list[Evidence], allowed_drivers: set[str]) -> list[str]:
    """Return a list of validation problems (empty = valid)."""
    problems: list[str] = []
    ids = {e.evidence_id: e for e in evidence}
    if not report.hypotheses:
        problems.append("Report contains no hypotheses")
    for idx, h in enumerate(report.hypotheses, 1):
        tag = f"Hypothesis {idx} ('{h.title}')"
        for eid in h.supporting_evidence_ids + h.contradicting_evidence_ids:
            if eid not in ids:
                problems.append(f"{tag} cites unknown evidence ID {eid}")
        for eid in h.contradicting_evidence_ids:
            e = ids.get(eid)
            if e and e.polarity == "supporting" and e.targets:
                problems.append(f"{tag} lists supporting-only evidence {eid} as contradicting")
        if h.driver_type not in allowed_drivers | {"none"}:
            problems.append(f"{tag} uses driver_type '{h.driver_type}' not present in candidate evidence")
        if h.evidence_strength != "INSUFFICIENT" and not h.supporting_evidence_ids:
            problems.append(f"{tag} has no supporting evidence")
        if h.claim_type == "fact":
            problems.append(f"{tag} presents a hypothesis as a verified fact")
        m = CAUSAL_PATTERN.search(h.explanation)
        if m:
            problems.append(f"{tag} uses causal-certainty language ('{m.group(0)}')")
        if re.search(r"\b\d{1,3}(\.\d+)?\s?%\s*(confidence|probability|likely|chance)", h.explanation, re.I):
            problems.append(f"{tag} states an uncalibrated confidence percentage")
    m = CAUSAL_PATTERN.search(report.investigation_summary)
    if m:
        problems.append(f"Summary uses causal-certainty language ('{m.group(0)}')")
    return problems
