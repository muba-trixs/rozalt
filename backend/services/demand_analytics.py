"""Module B — demand analytics on forecast vs recorded sales.

Recorded sales are what was sold (bounded by availability). They are never relabelled as
underlying demand; ``estimated_unconstrained_demand`` is produced only on stockout days and is
explicitly an estimate.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models as M


def load_demand(db: Session, sku_id: str | None = None, region: str | None = None,
                start: dt.date | None = None, end: dt.date | None = None,
                with_inventory: bool = False) -> pd.DataFrame:
    q = select(M.DemandRecord.date, M.DemandRecord.sku_id, M.DemandRecord.region_id,
               M.DemandRecord.forecast_qty, M.DemandRecord.recorded_sales_qty)
    if sku_id:
        q = q.where(M.DemandRecord.sku_id == sku_id)
    if region:
        q = q.where(M.DemandRecord.region_id == region)
    if start:
        q = q.where(M.DemandRecord.date >= start)
    if end:
        q = q.where(M.DemandRecord.date <= end)
    df = pd.DataFrame(db.execute(q).all(), columns=["date", "sku_id", "region", "forecast_qty", "recorded_sales_qty"])
    if with_inventory and not df.empty:
        iq = select(M.InventoryRecord.date, M.InventoryRecord.sku_id, M.InventoryRecord.region_id,
                    M.InventoryRecord.available_inventory, M.InventoryRecord.stockout_flag)
        if sku_id:
            iq = iq.where(M.InventoryRecord.sku_id == sku_id)
        if region:
            iq = iq.where(M.InventoryRecord.region_id == region)
        if start:
            iq = iq.where(M.InventoryRecord.date >= start)
        if end:
            iq = iq.where(M.InventoryRecord.date <= end)
        inv = pd.DataFrame(db.execute(iq).all(),
                           columns=["date", "sku_id", "region", "available_inventory", "stockout_flag"])
        df = df.merge(inv, on=["date", "sku_id", "region"], how="left")
    return df.sort_values(["sku_id", "region", "date"]).reset_index(drop=True)


def add_series_metrics(s: pd.DataFrame) -> pd.DataFrame:
    """Per-series metrics. Expects a single sku×region frame sorted by date."""
    s = s.copy()
    s["forecast_error"] = s["recorded_sales_qty"] - s["forecast_qty"]
    s["variance_pct"] = np.where(s["forecast_qty"] > 0, s["forecast_error"] / s["forecast_qty"] * 100, np.nan)
    s["rolling_mean_28"] = s["recorded_sales_qty"].rolling(28, min_periods=7).mean()
    s["rolling_std_28"] = s["recorded_sales_qty"].rolling(28, min_periods=7).std()
    # Seasonal baseline: median of the same weekday over the previous 8 weeks (lagged, so excludes today)
    dow = pd.to_datetime(s["date"]).dt.dayofweek
    baseline = pd.Series(np.nan, index=s.index)
    for d in range(7):
        idx = s.index[dow == d]
        baseline.loc[idx] = s.loc[idx, "recorded_sales_qty"].shift(1).rolling(8, min_periods=3).median()
    s["seasonal_baseline"] = baseline
    if "stockout_flag" in s.columns:
        ratio = (s["recorded_sales_qty"] / s["forecast_qty"]).where(~s["stockout_flag"].fillna(False).astype(bool))
        typical = ratio.rolling(56, min_periods=14).median().shift(1).bfill().fillna(1.0)
        est = s["forecast_qty"] * typical
        s["estimated_unconstrained_demand"] = np.where(
            s["stockout_flag"].fillna(False).astype(bool), np.maximum(est, s["recorded_sales_qty"]), np.nan)
    return s


def summarise_series(s: pd.DataFrame) -> dict:
    f, a = s["forecast_qty"].sum(), s["recorded_sales_qty"].sum()
    ape = (s["recorded_sales_qty"] - s["forecast_qty"]).abs() / s["forecast_qty"].replace(0, np.nan)
    resid = s["recorded_sales_qty"] / s["forecast_qty"].replace(0, np.nan) - 1
    return {
        "forecast_total": float(f),
        "recorded_sales_total": float(a),
        "variance_pct": float((a - f) / f * 100) if f else None,
        "mape_pct": float(ape.mean() * 100) if len(s) else None,
        "bias_pct": float(resid.mean() * 100) if len(s) else None,
        "residual_volatility_pct": float(resid.std() * 100) if len(s) > 1 else None,
        "sales_cv_pct": float(s["recorded_sales_qty"].std() / s["recorded_sales_qty"].mean() * 100)
        if len(s) > 1 and s["recorded_sales_qty"].mean() else None,
        "days": int(len(s)),
    }


def regional_comparison(db: Session, sku_id: str, start: dt.date | None, end: dt.date | None) -> list[dict]:
    df = load_demand(db, sku_id=sku_id, start=start, end=end)
    anomaly_counts = dict(db.execute(
        select(M.Anomaly.region_id, func.count()).where(M.Anomaly.sku_id == sku_id).group_by(M.Anomaly.region_id)
    ).all())
    out = []
    for region, s in df.groupby("region"):
        out.append({"region": region, **summarise_series(s), "anomaly_count": int(anomaly_counts.get(region, 0))})
    return sorted(out, key=lambda r: r["region"])


def data_date_range(db: Session) -> tuple[dt.date | None, dt.date | None]:
    return db.execute(select(func.min(M.DemandRecord.date), func.max(M.DemandRecord.date))).one()
