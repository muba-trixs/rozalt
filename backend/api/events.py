"""Event intelligence repository (events come from uploaded datasets — no live monitoring)."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models as M
from backend.database.session import get_db
from backend.schemas.common import ApiError, ok
from backend.services.settings_service import get_relevance_config

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def _unified(db: Session) -> list[dict]:
    cats = get_relevance_config(db)["categories"]
    out = []
    for e in db.scalars(select(M.ExternalEvent)):
        out.append({"event_id": e.event_id, "source_type": "external", "title": e.event_title,
                    "description": e.event_description, "category": e.event_category,
                    "driver_type": cats.get(e.event_category, cats["other"])["driver_type"],
                    "date": e.event_date.isoformat(), "end_date": (e.end_date or e.event_date).isoformat(),
                    "region": e.region_id, "source": e.source, "source_url": e.source_url,
                    "related_sku_ids": e.related_sku_ids or [], "related_category": e.related_category,
                    "severity": e.severity, "facility": None})
    for e in db.scalars(select(M.OperationalEvent)):
        out.append({"event_id": e.event_id, "source_type": "operational",
                    "title": f"{e.event_type.replace('_', ' ').title()} — {e.affected_facility or e.region_id}",
                    "description": e.description, "category": e.event_type,
                    "driver_type": cats.get(e.event_type, cats["other"])["driver_type"],
                    "date": e.date.isoformat(), "end_date": (e.end_date or e.date).isoformat(), "region": e.region_id,
                    "source": "Internal operations log", "source_url": None,
                    "related_sku_ids": e.related_sku_ids or [], "related_category": e.related_category,
                    "severity": e.severity, "facility": e.affected_facility})
    return out


def _relevance_index(db: Session) -> dict[str, dict]:
    rows = db.execute(
        select(M.CandidateDriver.source_id, func.max(M.CandidateDriver.relevance_score),
               func.count(func.distinct(M.CandidateDriver.investigation_id)))
        .group_by(M.CandidateDriver.source_id)
    ).all()
    return {sid: {"max_relevance": round(score, 3), "investigations": n} for sid, score, n in rows}


@router.get("")
def list_events(
    q: str | None = None, source_type: Literal["all", "external", "operational"] = "all",
    category: str | None = None, region: str | None = None, start: dt.date | None = None, end: dt.date | None = None,
    sort: Literal["date", "relevance"] = "date", page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
):
    events = _unified(db)
    rel = _relevance_index(db)
    if source_type != "all":
        events = [e for e in events if e["source_type"] == source_type]
    if category:
        cats = set(category.split(","))
        events = [e for e in events if e["category"] in cats]
    if region:
        regs = {r.lower() for r in region.split(",")}
        events = [e for e in events if e["region"].lower() in regs]
    if start:
        events = [e for e in events if e["end_date"] >= start.isoformat()]
    if end:
        events = [e for e in events if e["date"] <= end.isoformat()]
    if q:
        ql = q.lower()
        events = [e for e in events if ql in " ".join(str(e[k] or "") for k in
                                                       ("event_id", "title", "description", "region", "category",
                                                        "source")).lower()]
    for e in events:
        e["investigation_relevance"] = rel.get(e["event_id"])
    if sort == "relevance":
        events.sort(key=lambda e: -(e["investigation_relevance"] or {}).get("max_relevance", -1))
    else:
        events.sort(key=lambda e: e["date"], reverse=True)
    total = len(events)
    page_rows = events[(page - 1) * page_size: page * page_size]
    categories = sorted({e["category"] for e in _unified(db)})
    return ok(page_rows, total=total, page=page, page_size=page_size, categories=categories)


@router.get("/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    ev = next((e for e in _unified(db) if e["event_id"] == event_id), None)
    if not ev:
        raise ApiError(404, "not_found", f"Event {event_id} not found")
    links = db.execute(
        select(M.CandidateDriver, M.Investigation).join(
            M.Investigation, M.Investigation.investigation_id == M.CandidateDriver.investigation_id)
        .where(M.CandidateDriver.source_id == event_id).order_by(M.CandidateDriver.relevance_score.desc())
    ).all()
    ev["investigations"] = [
        {"investigation_id": inv.investigation_id, "anomaly_id": inv.anomaly_id, "relevance_score": c.relevance_score,
         "rank": c.rank, "above_threshold": (c.reasons or {}).get("above_threshold"), "components": c.component_scores}
        for c, inv in links
    ]
    return ok(ev)
