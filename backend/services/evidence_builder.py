"""Stage 6 — turn analytical results into typed, identifiable evidence objects.

kind:      fact (a recorded source record) | statistical (an exploratory association) |
           context (an estimate, assumption or data limitation)
targets:   per-candidate role — supporting or contradicting — with a heuristic weight. One evidence
           item may support one candidate and contradict another (polarity "mixed").
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.services.event_matching import CandidateEvent

INVENTORY_KEY = "derived:inventory_constraint"


def _days(n: int):
    import datetime as dt

    return dt.timedelta(days=n)


@dataclass
class Evidence:
    evidence_id: str
    kind: str
    title: str
    description: str
    source_table: str | None = None
    source_id: str | None = None
    targets: dict[str, dict] = field(default_factory=dict)
    payload: dict = field(default_factory=dict)

    @property
    def polarity(self) -> str:
        roles = {t["role"] for t in self.targets.values()}
        if not roles:
            return "neutral"
        return roles.pop() if len(roles) == 1 else "mixed"

    def to_dict(self, driver_lookup: dict[str, str]) -> dict:
        return {
            "evidence_id": self.evidence_id, "kind": self.kind, "polarity": self.polarity,
            "title": self.title, "description": self.description, "source_table": self.source_table,
            "source_id": self.source_id,
            "driver_types": sorted({driver_lookup.get(k, k.split(":")[-1]) for k in self.targets}),
            "payload": {**self.payload, "targets": self.targets},
        }


class EvidenceBuilder:
    def __init__(self, investigation_id: str):
        self.prefix = investigation_id
        self.items: list[Evidence] = []

    def add(self, kind: str, title: str, description: str, **kw) -> Evidence:
        ev = Evidence(f"{self.prefix}-EV-{len(self.items) + 1:02d}", kind, title, description, **kw)
        self.items.append(ev)
        return ev


def _p(p) -> str:
    if p is None:
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:+.1f}%"


def build_evidence(investigation_id: str, anomaly, product, candidates: list[CandidateEvent], stats: dict,
                   min_effect: float, onset_tolerance: int = 1) -> list[Evidence]:
    b = EvidenceBuilder(investigation_id)
    sign = -1 if anomaly.direction == "NEGATIVE" else 1
    ctx = stats["context"]

    b.add("fact", "Observed deviation",
          f"Recorded sales of {anomaly.sku_id} in {anomaly.region_id} were {ctx['recorded_sales_total']:,.0f} units "
          f"against a forecast of {ctx['forecast_total']:,.0f} ({_pct(ctx['variance_pct'])}) over "
          f"{ctx['window_days']} days from {anomaly.start_date} to {anomaly.end_date}.",
          source_table="demand_records", payload={"anomaly_id": anomaly.anomaly_id, "context": ctx})
    wc = ctx["window_comparison"]
    if not wc.get("insufficient_data"):
        b.add("statistical", "Deviation vs preceding 28 days",
              f"Mean daily residual moved from {_pct(wc['pre_mean_residual_pct'])} to "
              f"{_pct(wc['during_mean_residual_pct'])} (Welch t={wc['t_statistic']}, p={_p(wc['p_value'])}, "
              f"n={wc['n_pre']}/{wc['n_during']}). Descriptive only.", payload={"statistics": wc})

    for ev in candidates:
        key = ev.key
        b.add("fact", f"{ev.source_id}: {ev.title}",
              f"{ev.source or ev.source_table} records '{ev.title}' in {ev.region} from {ev.start} to {ev.end}. "
              f"{ev.description}",
              source_table=ev.source_table, source_id=ev.source_id,
              targets={key: {"role": "supporting", "weight": 0.0}},
              payload={"event": ev.to_dict()})

        c = ev.components
        if ev.start > anomaly.start_date + _days(max(ev.anticipation_days, onset_tolerance)):
            days = (ev.start - anomaly.start_date).days
            b.add("fact", f"{ev.source_id} began after onset",
                  f"{ev.source_id} began {days} day(s) after the deviation started on {anomaly.start_date}; it "
                  f"cannot account for the onset, although it may be associated with its continuation.",
                  source_table=ev.source_table, source_id=ev.source_id,
                  targets={key: {"role": "contradicting", "weight": 0.35}})
        if c.get("geographic", 1) == 0:
            b.add("fact", f"{ev.source_id} is outside the region",
                  f"{ev.source_id} concerns {ev.region}, not {anomaly.region_id}.",
                  source_table=ev.source_table, source_id=ev.source_id,
                  targets={key: {"role": "contradicting", "weight": 0.3}})
        if c.get("operational", 1) <= 0.1 + 1e-9:
            b.add("context", f"{ev.source_id} points the opposite way",
                  f"A {ev.category.replace('_', ' ')} would typically be expected to move recorded sales "
                  f"{ev.typical_direction.lower()}, but this deviation is {anomaly.direction.lower()}.",
                  source_table=ev.source_table, source_id=ev.source_id,
                  targets={key: {"role": "contradicting", "weight": 0.35}})
        elif c.get("operational", 1) <= 0.2 + 1e-9 or (c.get("product", 1) <= 0.3 and ev.mechanism == "demand_side") \
                or (c.get("product", 1) <= 0.3 and ev.mechanism == "unknown"):
            b.add("context", f"No plausible link from {ev.source_id} to {anomaly.sku_id}",
                  f"No recorded product, category or supply-chain linkage connects {ev.source_id} "
                  f"({ev.category.replace('_', ' ')}) to {product.product_name}.",
                  source_table=ev.source_table, source_id=ev.source_id,
                  targets={key: {"role": "contradicting", "weight": 0.25}})

        ew = stats["event_windows"].get(key)
        if ew and not ew.get("insufficient_data"):
            diff = ew["difference_pct_points"] or 0.0
            p_val = ew["p_value"]
            consistent = sign * diff >= min_effect * 100 and p_val is not None and p_val < 0.05
            b.add("statistical", f"Residual shift in {ev.source_id} window",
                  f"Mean daily residual in {ew['event_window'][0]}..{ew['event_window'][1]} was "
                  f"{_pct(ew['during_mean_residual_pct'])} vs {_pct(ew['pre_mean_residual_pct'])} before "
                  f"(Δ {diff:+.1f} pp, p={_p(ew['p_value'])}). "
                  + ("The deviation is concentrated in the event window." if consistent else
                     "No clear shift aligned with this event window."),
                  source_table=ev.source_table, source_id=ev.source_id,
                  targets={key: {"role": "supporting", "weight": 0.06}} if consistent else {},
                  payload={"statistics": ew})

        hc = stats["history"].get(key)
        if hc and hc["n_prior_events"] >= 2:
            ratio = hc["n_with_similar_deviation"] / hc["n_prior_events"]
            role = "supporting" if ratio >= 0.5 else ("contradicting" if hc["n_with_similar_deviation"] == 0 else None)
            b.add("statistical", f"Historical consistency for {ev.category.replace('_', ' ')} events",
                  f"{hc['n_with_similar_deviation']} of {hc['n_prior_events']} earlier {ev.category.replace('_', ' ')} "
                  f"events in {anomaly.region_id} coincided with a similar deviation for {anomaly.sku_id}.",
                  targets={key: {"role": role, "weight": 0.04 if role == "supporting" else 0.1}} if role else {},
                  payload={"statistics": hc})

    # Comparison group: same SKU, other regions
    pr = stats["peer_regions"]
    if not pr.get("insufficient_data"):
        targets = {}
        for ev in candidates:
            g = ev.components.get("geographic", 0)
            if pr["pattern"] == "localized":
                if g == 1.0:
                    targets[ev.key] = {"role": "supporting", "weight": 0.05}
                elif g == 0.5:
                    targets[ev.key] = {"role": "contradicting", "weight": 0.2}
            elif pr["pattern"] == "widespread":
                if g == 1.0:
                    targets[ev.key] = {"role": "contradicting", "weight": 0.25}
                elif g == 0.5:
                    targets[ev.key] = {"role": "supporting", "weight": 0.05}
        desc = {"localized": "did not show a comparable change — the deviation appears localized to "
                             f"{anomaly.region_id}.",
                "widespread": "showed a comparable change — the deviation is not specific to this region.",
                "partial": "showed a partial change in the same direction."}.get(pr["pattern"], "")
        b.add("statistical", "Comparison: same SKU in other regions",
              f"Across {pr['n_comparison_series']} other regions the mean residual changed by "
              f"{pr['comparison_mean_change_pct_points']:+.1f} pp vs {pr['focal_change_pct_points']:+.1f} pp here "
              f"(DiD {pr['did_estimate_pct_points']:+.1f} pp). The comparison group {desc}",
              targets=targets, payload={"statistics": pr})

    # Comparison group: other SKUs in the same category and region
    pc = stats["peer_category"]
    if not pc.get("insufficient_data"):
        targets = {}
        for ev in candidates:
            p = ev.components.get("product", 0)
            if pc["pattern"] == "localized" and p == 1.0:
                targets[ev.key] = {"role": "supporting", "weight": 0.04}
            elif pc["pattern"] == "localized" and p in (0.5, 0.7) and ev.mechanism == "demand_side":
                targets[ev.key] = {"role": "contradicting", "weight": 0.08}
            elif pc["pattern"] == "widespread" and p in (0.5, 0.7):
                targets[ev.key] = {"role": "supporting", "weight": 0.05}
            elif pc["pattern"] == "widespread" and p == 1.0 and ev.source_table != "promotions":
                targets[ev.key] = {"role": "contradicting", "weight": 0.08}
        b.add("statistical", f"Comparison: other {product.category} SKUs in {anomaly.region_id}",
              f"{pc['n_comparison_series']} other {product.category} SKUs changed by "
              f"{pc['comparison_mean_change_pct_points']:+.1f} pp on average vs {pc['focal_change_pct_points']:+.1f} pp "
              f"for {anomaly.sku_id} (pattern: {pc['pattern']}).",
              targets=targets, payload={"statistics": pc})

    # Inventory / availability
    inv = stats["inventory"]
    if not inv.get("insufficient_data"):
        supply = [ev for ev in candidates if ev.mechanism in ("supply_side", "demand_and_supply")]
        if inv["supply_constraint_observed"]:
            targets = {ev.key: {"role": "supporting", "weight": 0.1} for ev in supply}
            targets[INVENTORY_KEY] = {"role": "supporting", "weight": 0.1}
            b.add("fact", "Stockouts and reduced availability",
                  f"{inv['stockout_days_in_window']} of {inv['window_days']} days in the window recorded stockouts "
                  f"(vs {inv['stockout_days_pre_period']} in the prior 28 days); median inventory coverage changed "
                  f"by {_pct(inv['coverage_change_pct'])}.",
                  source_table="inventory_records", targets=targets, payload={"statistics": inv})
            if inv.get("estimated_unserved_units"):
                b.add("context", "Recorded sales understate demand on stockout days",
                      f"ESTIMATE: about {inv['estimated_unserved_units']:,.0f} units of demand may have gone unserved "
                      f"on stockout days ({inv['estimate_method']}). Underlying demand is not directly observed.",
                      source_table="inventory_records", payload={"statistics": inv})
        elif anomaly.direction == "NEGATIVE":
            targets = {ev.key: {"role": "contradicting", "weight": 0.3}
                       for ev in candidates if ev.mechanism == "supply_side"}
            b.add("fact", "Inventory remained available",
                  f"No material stockouts ({inv['stockout_days_in_window']} stockout days) and median coverage "
                  f"changed by {_pct(inv['coverage_change_pct'])}; a supply constraint is not observed in the data.",
                  source_table="inventory_records", targets=targets, payload={"statistics": inv})
        rho = inv.get("spearman_inventory_vs_sales", {})
        if rho.get("rho") is not None:
            b.add("statistical", "Inventory–sales association",
                  f"Spearman ρ between daily inventory and recorded sales around the window = {rho['rho']} "
                  f"(n={rho['n']}, p={_p(rho['p_value'])}). Association only; direction is not identified.",
                  source_table="inventory_records", payload={"statistics": {k: inv.get(k) for k in (
                      "spearman_inventory_vs_sales", "lagged_correlation_inventory_to_sales")}})
    else:
        b.add("context", "No inventory data", "Inventory records are unavailable for this SKU/region; "
              "supply-side explanations cannot be assessed.", payload={"statistics": inv})

    return b.items
