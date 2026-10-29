"""Module D — candidate event discovery and transparent heuristic relevance scoring.

Relevance = Σ weight_c × component_c with weights from ``config/relevance.yaml``.
Scores rank events for review; they are NOT probabilities that an event caused an anomaly.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend import models as M

NATIONAL = {"national", "all india", "pan-india", "pan india", "india"}
SEVERITY_SCORE = {"high": 1.0, "medium": 0.6, "low": 0.25}


@dataclass
class CandidateEvent:
    source_table: str
    source_id: str
    category: str
    driver_type: str
    mechanism: str
    typical_direction: str
    routine: bool
    anticipation_days: int
    title: str
    description: str
    start: dt.date
    end: dt.date
    region: str
    related_skus: list[str] = field(default_factory=list)
    related_category: str | None = None
    severity: str | None = None
    facility: str | None = None
    discount_pct: float | None = None
    source: str | None = None
    source_url: str | None = None
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source_table}:{self.source_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        d["key"] = self.key
        return d


def _category_info(cfg: dict, category: str) -> dict:
    return cfg["categories"].get(category, cfg["categories"]["other"])


def gather_events(db: Session, anomaly: M.Anomaly, cfg: dict) -> list[CandidateEvent]:
    lookback = int(cfg["window"]["lookback_days"])
    lo = anomaly.start_date - dt.timedelta(days=lookback)
    hi = anomaly.end_date
    out: list[CandidateEvent] = []

    ext = db.scalars(select(M.ExternalEvent).where(
        M.ExternalEvent.event_date <= hi,
        func.coalesce(M.ExternalEvent.end_date, M.ExternalEvent.event_date) >= lo,
    )).all()
    for e in ext:
        info = _category_info(cfg, e.event_category)
        out.append(CandidateEvent(
            source_table="external_events", source_id=e.event_id, category=e.event_category,
            driver_type=info["driver_type"], mechanism=info["mechanism"], typical_direction=info["direction"],
            routine=bool(info.get("routine")), anticipation_days=int(info.get("anticipation_days", 0)),
            title=e.event_title, description=e.event_description,
            start=e.event_date, end=e.end_date or e.event_date, region=e.region_id,
            related_skus=list(e.related_sku_ids or []), related_category=e.related_category, severity=e.severity,
            source=e.source, source_url=e.source_url,
        ))

    ops = db.scalars(select(M.OperationalEvent).where(
        M.OperationalEvent.date <= hi,
        func.coalesce(M.OperationalEvent.end_date, M.OperationalEvent.date) >= lo,
    )).all()
    for e in ops:
        info = _category_info(cfg, e.event_type)
        out.append(CandidateEvent(
            source_table="operational_events", source_id=e.event_id, category=e.event_type,
            driver_type=info["driver_type"], mechanism=info["mechanism"], typical_direction=info["direction"],
            routine=bool(info.get("routine")), anticipation_days=int(info.get("anticipation_days", 0)),
            title=f"{e.event_type.replace('_', ' ').title()} — "
                                                   f"{e.affected_facility or e.region_id}",
            description=e.description, start=e.date, end=e.end_date or e.date, region=e.region_id,
            related_skus=list(e.related_sku_ids or []), related_category=e.related_category, severity=e.severity,
            facility=e.affected_facility, source="Internal operations log",
        ))

    promos = db.scalars(select(M.Promotion).where(
        M.Promotion.sku_id == anomaly.sku_id, M.Promotion.region_id == anomaly.region_id,
        M.Promotion.start_date <= hi, M.Promotion.end_date >= lo,
    )).all()
    info = _category_info(cfg, "internal_promotion")
    for p in promos:
        out.append(CandidateEvent(
            source_table="promotions", source_id=f"PROMO-{p.id}", category="internal_promotion",
            driver_type=info["driver_type"], mechanism=info["mechanism"], typical_direction=info["direction"],
            routine=False, anticipation_days=0, title=f"Internal promotion: {p.promotion_type} ({p.discount_pct:g}% off)",
            description=f"{p.promotion_type} on {p.sku_id} in {p.region_id} from {p.start_date} to {p.end_date}, "
                        f"discount {p.discount_pct:g}%. Planned promotions are normally reflected in the forecast.",
            start=p.start_date, end=p.end_date, region=p.region_id, related_skus=[p.sku_id],
            discount_pct=p.discount_pct, source="Internal promotions calendar",
        ))
    return out


def _categories(value: str | None) -> set[str]:
    """Event category tags; several may be given separated by ';' or ','."""
    return {c.strip().lower() for c in (value or "").replace(",", ";").split(";") if c.strip()}


def _mentions(text: str, needle: str) -> bool:
    return bool(needle) and re.search(rf"\b{re.escape(needle.lower())}\b", text.lower()) is not None


def score_event(ev: CandidateEvent, anomaly: M.Anomaly, product: M.Product, cfg: dict) -> CandidateEvent:
    w = cfg["weights"]
    lookback = int(cfg["window"]["lookback_days"])
    lookahead = max(int(cfg["window"]["lookahead_days"]), 1)
    tolerance = int(cfg["window"].get("onset_tolerance_days", 1))
    onset = anomaly.start_date
    c: dict[str, float] = {}
    r: dict[str, str] = {}

    # Temporal
    if ev.start <= onset:
        lead = (onset - ev.start).days
        if ev.end >= onset - dt.timedelta(days=1):
            c["temporal"] = 1.0 if lead <= 3 else max(0.2, 1.0 - 0.8 * (lead - 3) / max(lookback - 3, 1))
            r["temporal"] = f"Started {lead} day(s) before onset and was active at onset"
        else:
            gap = (onset - ev.end).days
            c["temporal"] = max(0.0, 0.6 - 0.1 * gap)
            r["temporal"] = f"Ended {gap} day(s) before onset (lagged effect only)"
    elif (ev.start - onset).days <= tolerance:
        c["temporal"] = 0.85
        r["temporal"] = (f"Started {(ev.start - onset).days} day after detected onset — within the "
                         f"±{tolerance}-day onset tolerance")
    elif (ev.start - onset).days <= ev.anticipation_days:
        ahead = (ev.start - onset).days
        c["temporal"] = 0.9
        r["temporal"] = (f"Onset {ahead} day(s) before the event start — consistent with purchasing ahead of "
                         f"a {ev.category.replace('_', ' ')}")
    else:
        after = (ev.start - onset).days
        c["temporal"] = max(0.0, 0.5 * (1 - after / lookahead))
        r["temporal"] = f"Started {after} day(s) AFTER onset — cannot account for the onset"

    # Geographic
    reg = (ev.region or "").strip().lower()
    if reg == anomaly.region_id.lower():
        c["geographic"], r["geographic"] = 1.0, f"Same region ({anomaly.region_id})"
    elif reg in NATIONAL:
        c["geographic"], r["geographic"] = 0.5, "National / multi-region event"
    else:
        c["geographic"], r["geographic"] = 0.0, f"Different region ({ev.region})"

    # Product
    text = f"{ev.title} {ev.description}"
    cat = (product.category or "").lower()
    if anomaly.sku_id in ev.related_skus or _mentions(text, anomaly.sku_id) or _mentions(text, product.product_name):
        c["product"], r["product"] = 1.0, f"Event names {anomaly.sku_id}"
    elif cat and cat in _categories(ev.related_category):
        c["product"], r["product"] = 0.7, f"Targets the {product.category} category"
    elif ev.related_skus:
        c["product"], r["product"] = 0.1, "Names other SKUs only"
    elif ev.related_category:
        c["product"], r["product"] = 0.0, f"Targets a different category ({ev.related_category})"
    elif ev.mechanism in ("supply_side", "demand_and_supply"):
        c["product"], r["product"] = 0.5, "Region-wide event, not product specific"
    else:
        c["product"], r["product"] = 0.3, "No product linkage recorded"

    # Operational plausibility (mechanism × direction)
    if ev.routine:
        c["operational"], r["operational"] = 0.15, "Routine activity; impact not expected"
    elif ev.mechanism == "unknown":
        c["operational"], r["operational"] = 0.2, "No known mechanism for this event category"
    elif ev.typical_direction == "EITHER":
        c["operational"], r["operational"] = 0.5, f"{ev.category} can move sales either way"
    elif ev.typical_direction == anomaly.direction:
        c["operational"], r["operational"] = 1.0, (
            f"{ev.category.replace('_', ' ')} typically moves recorded sales {anomaly.direction.lower()} "
            f"({ev.mechanism.replace('_', ' ')})")
    else:
        c["operational"], r["operational"] = 0.1, (
            f"{ev.category.replace('_', ' ')} typically moves sales {ev.typical_direction.lower()}, "
            f"opposite to this anomaly")

    # Magnitude
    if ev.discount_pct is not None:
        mag = min(1.0, ev.discount_pct / 30)
        r["magnitude"] = f"Discount depth {ev.discount_pct:g}%"
    else:
        mag = SEVERITY_SCORE.get((ev.severity or "").lower(), 0.4)
        r["magnitude"] = f"Recorded severity: {ev.severity or 'not recorded'}"
    duration = (ev.end - ev.start).days + 1
    if duration >= 5:
        mag = min(1.0, mag + 0.1)
        r["magnitude"] += f"; lasted {duration} days"
    c["magnitude"] = mag

    ev.components = {k: round(v, 3) for k, v in c.items()}
    ev.reasons = r
    ev.score = round(sum(w[k] * c[k] for k in w), 4)
    return ev


def rank_events(db: Session, anomaly: M.Anomaly, cfg: dict) -> list[CandidateEvent]:
    product = db.get(M.Product, anomaly.sku_id)
    events = [score_event(e, anomaly, product, cfg) for e in gather_events(db, anomaly, cfg)]
    return sorted(events, key=lambda e: (-e.score, e.start, e.source_id))


def events_in_region_query(region: str):
    return or_(M.ExternalEvent.region_id == region, func.lower(M.ExternalEvent.region_id).in_(NATIONAL))
