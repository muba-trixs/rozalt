"""Effective configuration: YAML/code defaults overridden by values stored in app_settings."""
from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy.orm import Session

from backend.app.config import CONFIG_DIR
from backend.models import AppSetting

DETECTION_DEFAULTS: dict[str, Any] = {
    "z_threshold": 3.0,              # |robust z| for a day to be flagged by residual analysis
    "min_daily_variance": 0.12,      # |daily residual| (fraction) for a flagged day
    "min_run_days": 2,               # consecutive flagged days for a residual anomaly
    "extreme_z": 6.0,                # single-day anomalies allowed above this |z|
    "reference_window_days": 90,     # frozen reference baseline length
    "reference_lag_days": 28,        # reference ends this many days before the evaluated day
    "cusum_k": 0.5,                  # CUSUM allowance (in robust-sigma units)
    "cusum_h": 8.0,                  # CUSUM decision interval
    "cusum_recovery_days": 5,        # consecutive in-band days that close a sustained window
    "min_sustained_days": 5,
    "min_window_variance": 0.08,     # |window variance| (fraction) to keep any anomaly
    "severity_high": 0.25,
    "severity_medium": 0.15,
}


@lru_cache
def _relevance_defaults() -> dict[str, Any]:
    with open(CONFIG_DIR / "relevance.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _stored(db: Session, key: str) -> dict:
    row = db.get(AppSetting, key)
    return dict(row.value) if row else {}


def get_detection_config(db: Session) -> dict[str, Any]:
    cfg = dict(DETECTION_DEFAULTS)
    cfg.update({k: v for k, v in _stored(db, "detection").items() if k in DETECTION_DEFAULTS})
    return cfg


def get_relevance_config(db: Session) -> dict[str, Any]:
    cfg = copy.deepcopy(_relevance_defaults())
    stored = _stored(db, "relevance")
    if "weights" in stored:
        cfg["weights"].update(stored["weights"])
    if "hypothesis" in stored:
        cfg["hypothesis"].update(stored["hypothesis"])
    return cfg


def update_detection_config(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    unknown = set(values) - set(DETECTION_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown detection settings: {', '.join(sorted(unknown))}")
    merged = {**_stored(db, "detection"), **{k: float(v) for k, v in values.items()}}
    _save(db, "detection", merged)
    return get_detection_config(db)


def update_relevance_weights(db: Session, weights: dict[str, float]) -> dict[str, Any]:
    expected = set(_relevance_defaults()["weights"])
    if set(weights) != expected:
        raise ValueError(f"Weights must define exactly: {', '.join(sorted(expected))}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("Weights must be non-negative")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"Weights must sum to 1.0 (got {total:.3f})")
    stored = _stored(db, "relevance")
    stored["weights"] = {k: float(v) for k, v in weights.items()}
    _save(db, "relevance", stored)
    return get_relevance_config(db)


def reset_settings(db: Session) -> None:
    for key in ("detection", "relevance"):
        row = db.get(AppSetting, key)
        if row:
            db.delete(row)
    db.commit()


def _save(db: Session, key: str, value: dict) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()
