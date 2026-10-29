"""Anomaly explorer endpoints."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from backend import models as M
from backend.api.analytics import anomaly_with_investigation
from backend.database.session import get_db
from backend.schemas.common import ApiError, ok
from backend.services.anomaly_detection import run_detection
from backend.services.investigation_service import serialize_anomaly

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])

SORTABLE = {
    "start_date": M.Anomaly.start_date, "variance_pct": M.Anomaly.variance_pct, "sku_id": M.Anomaly.sku_id,
    "region": M.Anomaly.region_id, "duration_days": M.Anomaly.duration_days, "anomaly_id": M.Anomaly.anomaly_id,
    "abs_variance": func.abs(M.Anomaly.variance_pct), "peak_robust_z": func.abs(M.Anomaly.peak_robust_z),
    "severity": case((M.Anomaly.severity == "HIGH", 3), (M.Anomaly.severity == "MEDIUM", 2), else_=1),
    "status": M.Anomaly.status,
}


def _csv(v: str | None, upper: bool = False) -> list[str] | None:
    if not v:
        return None
    items = [x.strip() for x in v.split(",") if x.strip()]
    return [x.upper() for x in items] if upper else items


@router.get("")
def list_anomalies(
    sku_id: str | None = None, region: str | None = None, severity: str | None = None,
    direction: str | None = None, status: str | None = None, start: dt.date | None = None,
    end: dt.date | None = None, q: str | None = None,
    sort: str = "start_date", order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500), db: Session = Depends(get_db),
):
    query = select(M.Anomaly).join(M.Product, M.Product.sku_id == M.Anomaly.sku_id)
    for col, values in ((M.Anomaly.sku_id, _csv(sku_id)), (M.Anomaly.region_id, _csv(region)),
                        (M.Anomaly.severity, _csv(severity, True)), (M.Anomaly.direction, _csv(direction, True)),
                        (M.Anomaly.status, _csv(status, True))):
        if values:
            query = query.where(col.in_(values))
    if start:
        query = query.where(M.Anomaly.end_date >= start)
    if end:
        query = query.where(M.Anomaly.start_date <= end)
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(M.Anomaly.anomaly_id).like(like), func.lower(M.Anomaly.sku_id).like(like),
                                func.lower(M.Product.product_name).like(like),
                                func.lower(M.Anomaly.region_id).like(like)))
    col = SORTABLE.get(sort)
    if col is None:
        raise ApiError(400, "invalid_sort", f"Cannot sort by '{sort}'. Options: {', '.join(SORTABLE)}")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    query = query.order_by(col.desc() if order == "desc" else col.asc(), M.Anomaly.anomaly_id)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    products = {p.sku_id: p for p in db.scalars(select(M.Product))}
    return ok([anomaly_with_investigation(a, products.get(a.sku_id)) for a in rows],
              total=total, page=page, page_size=page_size)


@router.post("/detect")
def detect(db: Session = Depends(get_db)):
    return ok(run_detection(db))


@router.get("/{anomaly_id}")
def get_anomaly(anomaly_id: str, db: Session = Depends(get_db)):
    a = db.get(M.Anomaly, anomaly_id)
    if not a:
        raise ApiError(404, "not_found", f"Anomaly {anomaly_id} not found")
    d = serialize_anomaly(a, db.get(M.Product, a.sku_id))
    d["investigations"] = [{"investigation_id": i.investigation_id, "status": i.status,
                            "analysis_mode": i.analysis_mode, "summary": i.summary,
                            "created_at": i.created_at.isoformat() if i.created_at else None}
                           for i in sorted(a.investigations, key=lambda i: i.investigation_id, reverse=True)]
    return ok(d)
