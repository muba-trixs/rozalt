import datetime as dt

import numpy as np
import pandas as pd
import pytest

from backend.services.anomaly_detection import detect_series
from backend.services.settings_service import DETECTION_DEFAULTS
from backend.synthetic_data.generator import generate
from backend.synthetic_data.scenarios import SCENARIOS


def _series(effect_start=200, effect_len=30, effect=-0.18, n=365, seed=1):
    rng = np.random.default_rng(seed)
    dates = [dt.date(2025, 10, 1) + dt.timedelta(days=i) for i in range(n)]
    f = np.full(n, 1000.0) * np.exp(rng.normal(0, 0.03, n))
    a = 1000.0 * np.exp(rng.normal(0, 0.055, n))
    a[effect_start: effect_start + effect_len] *= 1 + effect
    return pd.DataFrame({"date": dates, "forecast_qty": f, "recorded_sales_qty": a})


def test_sustained_shift_detected_as_one_window():
    res = detect_series(_series(), DETECTION_DEFAULTS)
    neg = [r for r in res if r["direction"] == "NEGATIVE" and r["duration_days"] >= 20]
    assert len(neg) == 1
    w = neg[0]
    assert "cusum_level_shift" in w["detection_method"]
    assert abs((w["start_date"] - dt.date(2025, 10, 1)).days - 200) <= 3
    assert -24 < w["variance_pct"] < -12


def test_long_shift_not_absorbed_by_baseline():
    # 60-day level shift — longer than the reference lag — must still be covered end-to-end
    res = detect_series(_series(effect_len=60, effect=-0.2), DETECTION_DEFAULTS)
    neg = [r for r in res if r["direction"] == "NEGATIVE"]
    covered = sum(r["duration_days"] for r in neg)
    assert covered >= 50


def test_noise_only_series_has_few_anomalies():
    counts = [len(detect_series(_series(effect=0.0, seed=s), DETECTION_DEFAULTS)) for s in range(10)]
    assert sum(counts) <= 3


@pytest.fixture(scope="module")
def synthetic():
    return generate()


def test_all_scenarios_detected(synthetic):
    df = synthetic.demand.rename(columns={"forecast_quantity": "forecast_qty",
                                          "actual_sales_quantity": "recorded_sales_qty"})
    for sc in SCENARIOS:
        a, b = sc["window"]
        for sku in sc["affected_skus"]:
            s = df[(df.sku_id == sku) & (df.region == sc["region"])].sort_values("date")
            res = detect_series(s, DETECTION_DEFAULTS)
            hits = [r for r in res if r["direction"] == sc["direction"] and r["start_date"] <= b
                    and r["end_date"] >= a]
            assert hits, f"{sc['scenario_id']} {sku} not detected"
