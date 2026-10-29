"""Investigation endpoints: start, poll/stream real stage progress, read reports, analyst feedback."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend import models as M
from backend.database.session import get_db, get_session_factory
from backend.schemas.common import ApiError, ok
from backend.services.investigation_service import (
    InvestigationError,
    create_investigation,
    run_investigation,
    serialize_investigation,
)

router = APIRouter(prefix="/api/v1", tags=["investigations"])


class StartInvestigation(BaseModel):
    anomaly_id: str
    use_llm: bool = True


class FeedbackIn(BaseModel):
    verdict: Literal["CONFIRMED", "PLAUSIBLE", "REJECTED", "NEEDS_INVESTIGATION"]
    note: str | None = Field(default=None, max_length=2000)


def _run_in_background(factory: sessionmaker, investigation_id: str, use_llm: bool) -> None:
    db = factory()
    try:
        run_investigation(db, investigation_id, use_llm=use_llm)
    finally:
        db.close()


@router.post("/investigations", status_code=202)
def start(body: StartInvestigation, background: BackgroundTasks, db: Session = Depends(get_db),
          factory: sessionmaker = Depends(get_session_factory)):
    try:
        inv = create_investigation(db, body.anomaly_id)
    except InvestigationError as exc:
        raise ApiError(404, "not_found", str(exc))
    background.add_task(_run_in_background, factory, inv.investigation_id, body.use_llm)
    return ok({"investigation_id": inv.investigation_id, "status": inv.status, "stage_log": inv.stage_log})


@router.get("/investigations")
def list_investigations(anomaly_id: str | None = None, db: Session = Depends(get_db)):
    q = select(M.Investigation).order_by(M.Investigation.investigation_id.desc())
    if anomaly_id:
        q = q.where(M.Investigation.anomaly_id == anomaly_id)
    out = []
    products = {p.sku_id: p for p in db.scalars(select(M.Product))}
    for inv in db.scalars(q.limit(500)):
        a = inv.anomaly
        top = inv.hypotheses[0] if inv.hypotheses else None
        out.append({
            "investigation_id": inv.investigation_id, "anomaly_id": a.anomaly_id, "status": inv.status,
            "analysis_mode": inv.analysis_mode, "summary": inv.summary, "sku_id": a.sku_id,
            "product_name": products[a.sku_id].product_name if a.sku_id in products else None,
            "region": a.region_id, "start_date": a.start_date.isoformat(), "variance_pct": a.variance_pct,
            "severity": a.severity, "direction": a.direction,
            "top_hypothesis": {"title": top.title, "evidence_strength": top.evidence_strength,
                               "driver_type": top.driver_type} if top else None,
            "hypotheses": len(inv.hypotheses),
            "feedback_count": sum(len(h.feedback) for h in inv.hypotheses),
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "total_ms": (inv.timings or {}).get("total_ms"),
        })
    return ok(out)


@router.get("/investigations/{investigation_id}")
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(M.Investigation, investigation_id)
    if not inv:
        raise ApiError(404, "not_found", f"Investigation {investigation_id} not found")
    return ok(serialize_investigation(db, inv))


@router.get("/investigations/{investigation_id}/stream")
async def stream(investigation_id: str, factory: sessionmaker = Depends(get_session_factory)):
    """Server-sent events with the persisted stage log until the investigation finishes."""

    async def events():
        last = None
        for _ in range(1200):  # ~10 minutes max
            db = factory()
            try:
                inv = db.get(M.Investigation, investigation_id)
                if inv is None:
                    yield f"event: error\ndata: {json.dumps({'message': 'not found'})}\n\n"
                    return
                payload = json.dumps({"status": inv.status, "stage_log": inv.stage_log, "error": inv.error})
            finally:
                db.close()
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if json.loads(payload)["status"] != "RUNNING":
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/hypotheses/{hypothesis_id}/feedback", status_code=201)
def feedback(hypothesis_id: int, body: FeedbackIn, db: Session = Depends(get_db)):
    h = db.get(M.Hypothesis, hypothesis_id)
    if not h:
        raise ApiError(404, "not_found", f"Hypothesis {hypothesis_id} not found")
    fb = M.AnalystFeedback(hypothesis_id=h.id, verdict=body.verdict, note=(body.note or "").strip() or None)
    db.add(fb)
    db.commit()
    return ok({"id": fb.id, "hypothesis_id": h.id, "verdict": fb.verdict, "note": fb.note,
               "created_at": fb.created_at.isoformat() if fb.created_at else None})
