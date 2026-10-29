"""Module C — interpretable anomaly detection on forecast residuals.

Two complementary detectors run on the residual ratio e_t = recorded_sales / forecast − 1:

* ``forecast_residual`` — robust z-score of e_t against a *frozen, lagged* reference baseline
  (median / IQR of the window [t − lag − W, t − lag)). Because the reference ends ``lag`` days
  before the evaluated day, a level shift cannot be absorbed into its own baseline for at least
  ``lag`` days; a second pass then re-estimates the reference with first-pass anomaly days
  masked out, so long shifts stay anomalous for their full duration.
* ``cusum_level_shift`` — two-sided tabular CUSUM on the standardised residuals, which accumulates
  moderate but persistent deviations (e.g. −18% for 30 days) that single-day thresholds miss.

Windows from both detectors are merged per series.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend import models as M
from backend.services.demand_analytics import load_demand
from backend.services.settings_service import get_detection_config


@dataclass
class Window:
    start: int
    end: int
    direction: str
    methods: set[str]


def residual_reference(e: pd.Series, cfg: dict, mask: np.ndarray | None = None) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Lagged robust reference (median, IQR-sigma). Days in ``mask`` (already-flagged anomalies) are
    excluded so a persistent shift cannot contaminate its own baseline."""
    W, lag = int(cfg["reference_window_days"]), int(cfg["reference_lag_days"])
    clean = e.copy()
    if mask is not None:
        clean[mask] = np.nan
    roll = clean.rolling(W, min_periods=28)
    med = roll.median().shift(lag)
    q75 = roll.quantile(0.75).shift(lag)
    q25 = roll.quantile(0.25).shift(lag)
    sigma = ((q75 - q25) / 1.349).clip(lower=0.02)
    warmup = med.isna() & (np.arange(len(e)) < W + lag)
    # Warm-up uses the first available reference; long masked stretches carry the last clean reference forward
    return med.ffill().bfill().fillna(0.0), sigma.ffill().bfill().fillna(0.05), warmup


def _runs(mask: np.ndarray, max_gap: int = 1) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return runs
    s = p = idx[0]
    for i in idx[1:]:
        if i - p > max_gap + 1:
            runs.append((s, p))
            s = i
        p = i
    runs.append((s, p))
    return runs


def _residual_windows(z: np.ndarray, dev: np.ndarray, cfg: dict) -> list[Window]:
    out = []
    for sign, label in ((-1, "NEGATIVE"), (1, "POSITIVE")):
        flagged = (sign * z >= cfg["z_threshold"]) & (sign * dev >= cfg["min_daily_variance"])
        for a, b in _runs(flagged):
            length = b - a + 1
            if length >= cfg["min_run_days"] or np.max(sign * z[a: b + 1]) >= cfg["extreme_z"]:
                out.append(Window(a, b, label, {"forecast_residual"}))
    return out


def _cusum_windows(z: np.ndarray, cfg: dict) -> list[Window]:
    """Tabular CUSUM. A window opens where the statistic leaves zero and, once alarmed, closes after
    ``recovery_days`` consecutive days back within one robust sigma (so a large accumulated statistic
    cannot drag the window far past the end of the shift)."""
    k, h = cfg["cusum_k"], cfg["cusum_h"]
    recovery = int(cfg.get("cusum_recovery_days", 5))
    zc = np.clip(z, -6, 6)
    windows = []
    for sign, label in ((-1, "NEGATIVE"), (1, "POSITIVE")):
        x = sign * zc
        S, start, alarmed, last_hit, calm = 0.0, None, False, None, 0
        n = len(x)
        for i in range(n + 1):
            v = x[i] if i < n else -np.inf
            if i < n:
                prev = S
                S = max(0.0, S + v - k)
                if prev == 0.0 and S > 0 and not alarmed:
                    start = i
                if S > h:
                    alarmed = True
                if v >= 1.0:
                    last_hit, calm = i, 0
                else:
                    calm += 1
            closing = alarmed and (calm >= recovery or i == n)
            if closing and start is not None and last_hit is not None:
                bounds = _trim(x, start, last_hit)
                if bounds and bounds[1] - bounds[0] + 1 >= cfg["min_sustained_days"]:
                    windows.append(Window(bounds[0], bounds[1], label, {"cusum_level_shift"}))
                S, start, alarmed, last_hit, calm = 0.0, None, False, None, 0
            elif not alarmed and S == 0.0:
                start = None
    return windows


def _trim(x: np.ndarray, a: int, b: int, level: float = 2.0) -> tuple[int, int] | None:
    """Trim a CUSUM segment to its core: start at the first day whose 3-day forward mean reaches
    ``level`` sigma, end at the last day whose 3-day backward mean does (noise days at the edges
    otherwise stretch the window)."""
    start = next((i for i in range(a, b + 1) if x[i] >= level and x[i: min(i + 3, b + 1)].mean() >= level), None)
    end = next((i for i in range(b, a - 1, -1) if x[i] >= level and x[max(i - 2, a): i + 1].mean() >= level), None)
    if start is None or end is None or end < start:
        return None
    return int(start), int(end)


def _merge(windows: list[Window]) -> list[Window]:
    merged: list[Window] = []
    for w in sorted(windows, key=lambda w: (w.direction, w.start)):
        if merged and merged[-1].direction == w.direction and w.start <= merged[-1].end + 2:
            m = merged[-1]
            m.end = max(m.end, w.end)
            m.methods |= w.methods
        else:
            merged.append(Window(w.start, w.end, w.direction, set(w.methods)))
    return merged


def detect_series(s: pd.DataFrame, cfg: dict) -> list[dict]:
    """Detect anomaly windows in one sku×region series (sorted by date)."""
    s = s.reset_index(drop=True)
    f = s["forecast_qty"].to_numpy(dtype=float)
    a = s["recorded_sales_qty"].to_numpy(dtype=float)
    e = pd.Series(np.where(f > 0, a / np.maximum(f, 1e-9) - 1, 0.0))
    mask = None
    for _ in range(2):  # pass 2 re-estimates the reference with pass-1 anomaly days masked out
        ref, sigma, warmup = residual_reference(e, cfg, mask)
        dev = (e - ref).to_numpy()
        z = dev / sigma.to_numpy()
        windows = _merge(_residual_windows(z, dev, cfg) + _cusum_windows(z, cfg))
        mask = np.zeros(len(e), dtype=bool)
        for w in windows:
            mask[w.start: w.end + 1] = True
    results = []
    for w in windows:
        sl = slice(w.start, w.end + 1)
        fsum, asum = f[sl].sum(), a[sl].sum()
        var = (asum - fsum) / fsum if fsum else 0.0
        if abs(var) < cfg["min_window_variance"] or (var < 0) != (w.direction == "NEGATIVE"):
            continue
        zz = z[sl]
        peak = int(np.argmax(np.abs(zz)))
        sev = "HIGH" if abs(var) >= cfg["severity_high"] else ("MEDIUM" if abs(var) >= cfg["severity_medium"] else "LOW")
        methods = sorted(w.methods)
        results.append({
            "start_date": s.at[w.start, "date"], "end_date": s.at[w.end, "date"],
            "peak_date": s.at[w.start + peak, "date"], "duration_days": int(w.end - w.start + 1),
            "forecast_qty": float(fsum), "recorded_sales_qty": float(asum), "variance_pct": round(var * 100, 2),
            "peak_robust_z": round(float(zz[peak]), 2), "direction": w.direction, "severity": sev,
            "detection_method": "+".join(methods),
            "details": {
                "methods": methods,
                "mean_daily_residual_pct": round(float(np.mean(dev[sl])) * 100, 2),
                "reference_median_residual_pct": round(float(ref.iloc[w.start]) * 100, 2),
                "reference_sigma_pct": round(float(sigma.iloc[w.start]) * 100, 2),
                "reference_warmup": bool(warmup.iloc[w.start]),
                "thresholds": {k: cfg[k] for k in ("z_threshold", "min_daily_variance", "cusum_k", "cusum_h",
                                                   "reference_window_days", "reference_lag_days")},
            },
        })
    return results


def detect_all(db: Session, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or get_detection_config(db)
    df = load_demand(db)
    found = []
    for (sku, region), s in df.groupby(["sku_id", "region"], sort=True):
        for r in detect_series(s, cfg):
            found.append({"sku_id": sku, "region_id": region, **r})
    return sorted(found, key=lambda r: (r["start_date"], r["sku_id"], r["region_id"]))


def run_detection(db: Session, cfg: dict | None = None) -> dict:
    """Replace un-investigated anomalies with a fresh detection run. Investigated anomalies are kept."""
    cfg = cfg or get_detection_config(db)
    kept = db.scalars(select(M.Anomaly).where(M.Anomaly.investigations.any())).all()
    db.execute(delete(M.Anomaly).where(~M.Anomaly.investigations.any()))
    used_ids = {a.anomaly_id for a in kept}
    next_num = max([int(i.split("-")[1]) for i in used_ids] + [1000]) + 1

    created = 0
    for r in detect_all(db, cfg):
        overlap = any(k.sku_id == r["sku_id"] and k.region_id == r["region_id"] and k.start_date <= r["end_date"]
                      and k.end_date >= r["start_date"] for k in kept)
        if overlap:
            continue
        db.add(M.Anomaly(anomaly_id=f"ANM-{next_num}", status="NEW", **r))
        next_num += 1
        created += 1
    db.commit()
    return {"created": created, "kept_investigated": len(kept), "config": cfg}
