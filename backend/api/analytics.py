"""Demand analytics endpoints. Field names keep forecast, recorded sales and estimated demand distinct."""
from __future__ import annotations

import datetime as dt

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models as M
from backend.database.session import get_db
from backend.schemas.common import ApiError, ok
from backend.services.demand_analytics import (
    add_series_metrics,
    data_date_range,
    load_demand,
    regional_comparison,
    summarise_series,
)
from backend.services.investigation_service import serialize_anomaly

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

SEVERITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 2)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def anomaly_with_investigation(a: M.Anomaly, product: M.Product | None) -> dict:
    d = serialize_anomaly(a, product)
    latest = max(a.investigations, key=lambda i: i.investigation_id, default=None)
    d["latest_investigation_id"] = latest.investigation_id if latest else None
    d["latest_investigation_status"] = latest.status if latest else None
    return d


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    def count_anomalies(cond=None) -> int:
        q = select(func.count()).select_from(M.Anomaly)
        return db.scalar(q.where(cond) if cond is not None else q)

    kpis = {
        "skus_monitored": db.scalar(select(func.count()).select_from(M.Product)),
        "regions_monitored": db.scalar(select(func.count()).select_from(M.Region)),
        "active_anomalies": count_anomalies(),
        "high_severity": count_anomalies(M.Anomaly.severity == "HIGH"),
        "uninvestigated": count_anomalies(M.Anomaly.status == "NEW"),
        "negative_anomalies": count_anomalies(M.Anomaly.direction == "NEGATIVE"),
        "positive_anomalies": count_anomalies(M.Anomaly.direction == "POSITIVE"),
        "completed_investigations": db.scalar(select(func.count()).select_from(M.Investigation)
                                              .where(M.Investigation.status == "COMPLETED")),
    }
    anomalies = db.scalars(select(M.Anomaly)).all()
    products = {p.sku_id: p for p in db.scalars(select(M.Product))}
    top = sorted(anomalies, key=lambda a: (SEVERITY_RANK.get(a.severity, 3), -abs(a.variance_pct)))[:12]
    lo, hi = data_date_range(db)
    default = top[0] if top else None
    return ok({
        "kpis": kpis,
        "top_anomalies": [anomaly_with_investigation(a, products.get(a.sku_id)) for a in top],
        "default_series": {"sku_id": default.sku_id, "region": default.region_id} if default else None,
        "date_range": [lo.isoformat() if lo else None, hi.isoformat() if hi else None],
    })


@router.get("/skus")
def skus(db: Session = Depends(get_db)):
    regions: dict[str, list[str]] = {}
    for sku, region in db.execute(select(M.DemandRecord.sku_id, M.DemandRecord.region_id).distinct()):
        regions.setdefault(sku, []).append(region)
    return ok([{"sku_id": p.sku_id, "product_name": p.product_name, "category": p.category, "brand": p.brand,
                "regions": sorted(regions.get(p.sku_id, []))}
               for p in db.scalars(select(M.Product).order_by(M.Product.sku_id))])


@router.get("/regions")
def regions(db: Session = Depends(get_db)):
    return ok(list(db.scalars(select(M.Region.region_id).order_by(M.Region.region_id))))


@router.get("/timeseries")
def timeseries(sku_id: str, region: str, start: dt.date | None = None, end: dt.date | None = None,
               db: Session = Depends(get_db)):
    product = db.get(M.Product, sku_id)
    if not product:
        raise ApiError(404, "unknown_sku", f"SKU {sku_id} not found")
    full = load_demand(db, sku_id, region, with_inventory=True)
    if full.empty:
        raise ApiError(404, "no_data", f"No demand records for {sku_id} in {region}")
    s = add_series_metrics(full)
    if start:
        s = s[s.date >= start]
    if end:
        s = s[s.date <= end]
    cols = ["date", "forecast_qty", "recorded_sales_qty", "seasonal_baseline", "rolling_mean_28", "rolling_std_28",
            "forecast_error", "variance_pct", "available_inventory", "stockout_flag", "estimated_unconstrained_demand"]
    present = [c for c in cols if c in s.columns]
    points = [{c: _clean(v) for c, v in zip(present, row)} for row in s[present].itertuples(index=False)]
    anomalies = db.scalars(select(M.Anomaly).where(M.Anomaly.sku_id == sku_id, M.Anomaly.region_id == region)
                           .order_by(M.Anomaly.start_date)).all()
    return ok({
        "sku_id": sku_id, "product_name": product.product_name, "category": product.category, "region": region,
        "points": points, "summary": summarise_series(s),
        "anomalies": [anomaly_with_investigation(a, product) for a in anomalies],
        "quantity_definitions": {
            "forecast_qty": "Planned quantity from the demand plan",
            "recorded_sales_qty": "Observed sales (bounded by available inventory)",
            "estimated_unconstrained_demand": "ESTIMATE on stockout days only; underlying demand is not observed",
        },
    })


@router.get("/regional")
def regional(sku_id: str, start: dt.date | None = None, end: dt.date | None = None, db: Session = Depends(get_db)):
    if not db.get(M.Product, sku_id):
        raise ApiError(404, "unknown_sku", f"SKU {sku_id} not found")
    return ok(regional_comparison(db, sku_id, start, end))


@router.get("/portfolio")
def portfolio(region: str | None = None, category: str | None = None, db: Session = Depends(get_db)):
    df = load_demand(db, region=region)
    if category:
        skus_in = set(db.scalars(select(M.Product.sku_id).where(M.Product.category == category)))
        df = df[df.sku_id.isin(skus_in)]
    if df.empty:
        return ok({"points": []})
    g = df.groupby("date")[["forecast_qty", "recorded_sales_qty"]].sum().reset_index()
    return ok({"points": [{"date": r.date.isoformat(), "forecast_qty": round(r.forecast_qty, 1),
                           "recorded_sales_qty": round(r.recorded_sales_qty, 1)} for r in g.itertuples()]})
