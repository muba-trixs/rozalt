"""Module E — exploratory statistics for an anomaly and its candidate events.

Every result is descriptive/exploratory: it records method, sample sizes, assumptions and caveats.
p-values are reported as descriptive indicators, not as confirmatory tests, and no result here
establishes causation. Isolated events are analysed with event-window comparisons rather than
correlations; correlations are computed only for continuous paired series with n ≥ 14.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
from scipy import stats

from backend.services.event_matching import CandidateEvent

PRE_DAYS = 28
MIN_N = 3
MIN_CORR_N = 14


def _f(x) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    # keep significant digits for tiny values (e.g. p-values) instead of rounding them to 0
    return float(f"{v:.3g}") if 0 < abs(v) < 1e-3 else round(v, 4)


def residual(df: pd.DataFrame) -> pd.Series:
    return df["recorded_sales_qty"] / df["forecast_qty"].replace(0, np.nan) - 1


def window_comparison(pre: pd.Series, during: pd.Series, label: str) -> dict:
    """Welch two-sample comparison of daily residual ratios (exploratory)."""
    pre, during = pre.dropna(), during.dropna()
    res = {
        "method": "welch_t_test_on_daily_residuals",
        "label": label,
        "n_pre": int(len(pre)), "n_during": int(len(during)),
        "assumptions": [
            "Daily residuals (recorded sales / forecast − 1) are approximately independent",
            "The pre-period is representative of normal forecast error",
        ],
        "caveats": ["Exploratory comparison; p-value is descriptive, not confirmatory",
                    "A difference in timing does not establish that the event produced the change"],
    }
    if len(pre) < MIN_N or len(during) < MIN_N:
        res.update({"insufficient_data": True, "reason": f"Need ≥{MIN_N} days in each window"})
        return res
    t, p = stats.ttest_ind(during, pre, equal_var=False)
    pooled = math.sqrt((pre.var(ddof=1) + during.var(ddof=1)) / 2) or 1e-9
    res.update({
        "insufficient_data": False,
        "pre_mean_residual_pct": _f(pre.mean() * 100), "during_mean_residual_pct": _f(during.mean() * 100),
        "difference_pct_points": _f((during.mean() - pre.mean()) * 100),
        "t_statistic": _f(t), "p_value": _f(p), "cohens_d": _f((during.mean() - pre.mean()) / pooled),
    })
    return res


def anomaly_context(series: pd.DataFrame, anomaly) -> dict:
    s = series.copy()
    s["e"] = residual(s)
    a0, a1 = anomaly.start_date, anomaly.end_date
    pre = s[(s.date < a0) & (s.date >= a0 - dt.timedelta(days=PRE_DAYS))]
    during = s[(s.date >= a0) & (s.date <= a1)]
    comp = window_comparison(pre["e"], during["e"], "anomaly window vs preceding 28 days")
    hist = s[s.date < a0 - dt.timedelta(days=7)]["e"]
    ctx = {
        "window_days": int(len(during)),
        "forecast_total": _f(during["forecast_qty"].sum()),
        "recorded_sales_total": _f(during["recorded_sales_qty"].sum()),
        "variance_pct": _f((during["recorded_sales_qty"].sum() / during["forecast_qty"].sum() - 1) * 100)
        if len(during) else None,
        "historical_residual_sd_pct": _f(hist.std() * 100) if len(hist) > 10 else None,
        "historical_abs_residual_p95_pct": _f(hist.abs().quantile(0.95) * 100) if len(hist) > 10 else None,
        "window_comparison": comp,
    }
    return ctx


def event_window(series: pd.DataFrame, anomaly, ev: CandidateEvent) -> dict:
    s = series.copy()
    s["e"] = residual(s)
    a0, a1 = anomaly.start_date, anomaly.end_date
    d0 = max(ev.start, a0)
    d1 = min(max(ev.end, a0) + dt.timedelta(days=3), a1)
    pre = s[(s.date < min(ev.start, a0)) & (s.date >= min(ev.start, a0) - dt.timedelta(days=PRE_DAYS))]
    during = s[(s.date >= d0) & (s.date <= d1)]
    res = window_comparison(pre["e"], during["e"], f"event window {d0}..{d1} vs 28 days before")
    res["event_window"] = [d0.isoformat(), d1.isoformat()]
    res["onset_lag_days"] = (a0 - ev.start).days
    return res


def peer_comparison(peers: pd.DataFrame, focal: pd.DataFrame, anomaly, group_label: str) -> dict:
    """Difference-in-differences style comparison against a comparison group (exploratory)."""
    a0, a1 = anomaly.start_date, anomaly.end_date
    res = {
        "method": "difference_in_differences_on_mean_residuals",
        "comparison_group": group_label,
        "assumptions": ["Comparison series would have tracked the focal series absent a localized driver",
                        "Comparison series are not themselves affected by the same driver"],
        "caveats": ["Exploratory; parallel-trends assumption is not tested",
                    "Small comparison groups give unstable estimates"],
    }
    if peers.empty:
        res.update({"insufficient_data": True, "reason": "No comparison series available"})
        return res
    peers = peers.copy()
    peers["e"] = residual(peers)
    f = focal.copy()
    f["e"] = residual(f)

    def change(df):
        pre = df[(df.date < a0) & (df.date >= a0 - dt.timedelta(days=PRE_DAYS))]["e"].mean()
        dur = df[(df.date >= a0) & (df.date <= a1)]["e"].mean()
        return pre, dur

    fp, fd = change(f)
    per_group = []
    for key, g in peers.groupby("group"):
        gp, gd = change(g)
        per_group.append({"group": key, "pre_mean_residual_pct": _f(gp * 100),
                          "during_mean_residual_pct": _f(gd * 100), "change_pct_points": _f((gd - gp) * 100)})
    changes = [g["change_pct_points"] for g in per_group if g["change_pct_points"] is not None]
    peer_change = float(np.mean(changes)) if changes else float("nan")
    focal_change = (fd - fp) * 100
    share = None
    if changes and abs(focal_change) > 1e-9:
        share = peer_change / focal_change
    res.update({
        "insufficient_data": len(changes) == 0,
        "n_comparison_series": len(changes),
        "focal_change_pct_points": _f(focal_change),
        "comparison_mean_change_pct_points": _f(peer_change),
        "did_estimate_pct_points": _f(focal_change - peer_change) if changes else None,
        "comparison_share_of_focal_change": _f(share),
        "comparison_series": per_group,
        # localized: comparison group moved < 40% as much as the focal series in the same direction
        "pattern": None if share is None else ("localized" if share < 0.4 else
                                              ("widespread" if share >= 0.6 else "partial")),
    })
    return res


def inventory_analysis(series: pd.DataFrame, anomaly) -> dict:
    res = {
        "method": "stockout_count_coverage_ratio_and_spearman",
        "assumptions": ["available_inventory is measured at the start of each day",
                        "Coverage = available inventory / forecast"],
        "caveats": ["Recorded sales cannot exceed available inventory; on stockout days underlying demand "
                    "is not observed", "Correlation between inventory and sales is not evidence of direction"],
    }
    if "available_inventory" not in series.columns or series["available_inventory"].isna().all():
        res.update({"insufficient_data": True, "reason": "No inventory records for this SKU/region"})
        return res
    s = series.dropna(subset=["available_inventory"]).copy()
    a0, a1 = anomaly.start_date, anomaly.end_date
    s["coverage"] = s["available_inventory"] / s["forecast_qty"].replace(0, np.nan)
    pre = s[(s.date < a0) & (s.date >= a0 - dt.timedelta(days=PRE_DAYS))]
    dur = s[(s.date >= a0) & (s.date <= a1)]
    stockout_days = int(dur["stockout_flag"].fillna(False).astype(bool).sum())
    pre_stockouts = int(pre["stockout_flag"].fillna(False).astype(bool).sum())
    cov_pre, cov_dur = pre["coverage"].median(), dur["coverage"].median()
    res.update({
        "insufficient_data": False,
        "stockout_days_in_window": stockout_days,
        "window_days": int(len(dur)),
        "stockout_days_pre_period": pre_stockouts,
        "median_coverage_pre": _f(cov_pre), "median_coverage_window": _f(cov_dur),
        "coverage_change_pct": _f((cov_dur / cov_pre - 1) * 100) if cov_pre else None,
    })
    if "estimated_unconstrained_demand" in dur.columns:
        est = dur["estimated_unconstrained_demand"].dropna()
        if len(est):
            sales_on_stockout = dur.loc[est.index, "recorded_sales_qty"].sum()
            res["estimated_unconstrained_demand_on_stockout_days"] = _f(est.sum())
            res["estimated_unserved_units"] = _f(est.sum() - sales_on_stockout)
            res["estimate_method"] = ("forecast × median sales/forecast ratio on preceding in-stock days "
                                      "(ESTIMATE — unconstrained demand is not observed)")
    span = s[(s.date >= a0 - dt.timedelta(days=30)) & (s.date <= a1 + dt.timedelta(days=7))]
    if len(span) >= MIN_CORR_N:
        rho, p = stats.spearmanr(span["available_inventory"], span["recorded_sales_qty"])
        res["spearman_inventory_vs_sales"] = {"rho": _f(rho), "p_value": _f(p), "n": int(len(span))}
        lags = []
        inv = span["available_inventory"].reset_index(drop=True)
        sales = span["recorded_sales_qty"].reset_index(drop=True)
        for lag in range(0, 8):
            if len(span) - lag >= MIN_CORR_N:
                r = stats.pearsonr(inv[: len(inv) - lag], sales[lag:])[0] if lag else stats.pearsonr(inv, sales)[0]
                lags.append({"lag_days": lag, "pearson_r": _f(r)})
        res["lagged_correlation_inventory_to_sales"] = lags
    else:
        res["spearman_inventory_vs_sales"] = {"insufficient_data": True, "n": int(len(span))}
    res["supply_constraint_observed"] = bool(stockout_days >= 2 or (res["coverage_change_pct"] or 0) <= -35)
    return res


def historical_consistency(series: pd.DataFrame, anomaly, ev: CandidateEvent, prior_events: list[dict],
                           min_effect: float) -> dict:
    """Did earlier events of the same category in the same region coincide with deviations for this SKU?"""
    s = series.copy()
    s["e"] = residual(s)
    sign = -1 if anomaly.direction == "NEGATIVE" else 1
    hits, checked = 0, []
    for p in prior_events:
        start = dt.date.fromisoformat(p["start"])
        win = s[(s.date >= start) & (s.date <= start + dt.timedelta(days=14))]["e"]
        base = s[(s.date < start) & (s.date >= start - dt.timedelta(days=PRE_DAYS))]["e"]
        if len(win) < MIN_N or len(base) < MIN_N:
            continue
        diff = win.mean() - base.mean()
        hit = sign * diff >= min_effect
        hits += int(hit)
        checked.append({"event_id": p["id"], "start": p["start"], "difference_pct_points": _f(diff * 100),
                        "deviation_in_same_direction": bool(hit)})
    return {
        "method": "prior_same_category_event_windows",
        "category": ev.category,
        "n_prior_events": len(checked),
        "n_with_similar_deviation": hits,
        "prior_events": checked,
        "insufficient_data": len(checked) == 0,
        "caveats": ["Small numbers of prior events; consistency is suggestive only"],
    }
