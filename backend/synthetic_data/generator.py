"""Deterministic synthetic FMCG dataset generator.

Produces the five CSV datasets in the ingestion formats plus ``ground_truth.json``.
Three quantities are generated separately and never conflated:
  * forecast        — what planners expected (knows seasonality, holidays and planned promotions)
  * true demand     — unconstrained consumer demand (NOT exported; never observed by the engine)
  * recorded sales  — min(true demand, available inventory)
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backend.synthetic_data import scenarios as S

WEEKLY = np.array([0.94, 0.95, 0.97, 1.00, 1.04, 1.08, 1.02])  # Mon..Sun


@dataclass
class SyntheticDataset:
    demand: pd.DataFrame
    inventory: pd.DataFrame
    promotions: pd.DataFrame
    operational_events: pd.DataFrame
    external_events: pd.DataFrame
    ground_truth: dict

    def frames(self) -> dict[str, pd.DataFrame]:
        return {
            "demand": self.demand,
            "inventory": self.inventory,
            "promotions": self.promotions,
            "operational_events": self.operational_events,
            "external_events": self.external_events,
        }


def _dates() -> pd.DatetimeIndex:
    return pd.date_range(S.START_DATE, S.END_DATE, freq="D")


def _protected_windows() -> list[tuple[str, dt.date, dt.date]]:
    """(region, start, end) windows padded so background noise never overlaps scenarios."""
    out = []
    for sc in S.SCENARIOS:
        a, b = sc["window"]
        out.append((sc["region"], a - dt.timedelta(days=30), b + dt.timedelta(days=10)))
    return out


def _is_protected(region: str, start: dt.date, end: dt.date) -> bool:
    for r, a, b in _protected_windows():
        if (region == r or region == "National") and start <= b and end >= a:
            return True
    return False


def _routine_promotions(rng: np.random.Generator) -> list[dict]:
    promos = []
    days = (S.END_DATE - S.START_DATE).days
    for sku_id, *_ in S.CATALOG:
        for region in S.REGIONS:
            for _ in range(int(rng.integers(2, 5))):
                start = S.START_DATE + dt.timedelta(days=int(rng.integers(20, days - 15)))
                end = start + dt.timedelta(days=int(rng.integers(6, 11)))
                if _is_protected(region, start, end):
                    continue
                if any(p["sku_id"] == sku_id and p["region"] == region and start <= p["end_date"]
                       and end >= p["start_date"] for p in promos):
                    continue
                promos.append({
                    "start_date": start, "end_date": end, "sku_id": sku_id, "region": region,
                    "promotion_type": str(rng.choice(["Price Discount", "Display Promotion", "Multi-buy"])),
                    "discount_percentage": float(rng.choice([10.0, 12.5, 15.0, 20.0, 25.0])),
                })
    return promos + [dict(p) for p in S.SCENARIO_PROMOTIONS]


def _background_events(rng: np.random.Generator) -> tuple[list[dict], list[dict]]:
    categories = sorted({c for _, _, c, _ in S.CATALOG})
    regions = list(S.REGIONS)
    ext, ops = [], []
    days = (S.END_DATE - S.START_DATE).days
    n = 0
    while len(ext) < 28 and n < 500:
        n += 1
        title, cat, region_t, rel_cat_t, sev = S.BACKGROUND_EXTERNAL[int(rng.integers(len(S.BACKGROUND_EXTERNAL)))]
        region = region_t.format(region=str(rng.choice(regions)))
        rel_cat = rel_cat_t.format(category=str(rng.choice(categories)))
        start = S.START_DATE + dt.timedelta(days=int(rng.integers(5, days - 5)))
        end = start + dt.timedelta(days=int(rng.integers(0, 4)))
        if _is_protected(region, start, end):
            continue
        ext.append({
            "event_id": f"EXT-{1000 + len(ext) + 1}", "event_date": start, "end_date": end,
            "event_title": f"{title}" + (f" ({region})" if region != "National" else ""),
            "event_description": f"{title}. Routine market development with no specific product linkage reported.",
            "event_category": cat, "region": region, "source": "Market Monitor",
            "source_url": f"https://example.com/monitor/{1000 + len(ext) + 1}", "related_sku_ids": "",
            "related_category": rel_cat, "severity": sev,
        })
    n = 0
    while len(ops) < 14 and n < 500:
        n += 1
        etype, desc, sev = S.BACKGROUND_OPERATIONAL[int(rng.integers(len(S.BACKGROUND_OPERATIONAL)))]
        region = str(rng.choice(regions))
        facility = str(rng.choice(S.FACILITIES[region]))
        start = S.START_DATE + dt.timedelta(days=int(rng.integers(5, days - 5)))
        if _is_protected(region, start, start):
            continue
        ops.append({
            "event_id": f"OPS-{4000 + len(ops) + 1}", "date": start, "end_date": start, "event_type": etype,
            "region": region, "affected_facility": facility, "description": desc.format(facility=facility),
            "related_sku_ids": "", "related_category": "", "severity": sev,
        })
    return ext, ops


def generate(seed: int = S.SEED) -> SyntheticDataset:
    rng = np.random.default_rng(seed)
    dates = _dates()
    n = len(dates)
    doy = dates.dayofyear.to_numpy()
    dow = dates.dayofweek.to_numpy()
    t = np.arange(n)
    date_list = [x.date() for x in dates]

    promotions = _routine_promotions(rng)
    ext_bg, ops_bg = _background_events(rng)

    demand_rows: list[dict] = []
    inventory_rows: list[dict] = []

    for sku_id, name, category, base in S.CATALOG:
        amp, peak = S.SEASONALITY[category]
        annual = 1 + amp * np.cos(2 * np.pi * (doy - peak) / 365.25)
        weekly = WEEKLY * (1 + rng.normal(0, 0.01, 7))
        trend = 1 + rng.uniform(-0.02, 0.05) * t / n
        holiday = np.ones(n)
        for h in S.KNOWN_HOLIDAYS:
            if category in h["categories"]:
                mask = (dates.date >= h["start"]) & (dates.date <= h["end"])
                holiday[mask] *= 1 + h["lift"]

        for region, rfactor in S.REGIONS.items():
            level = base * rfactor * rng.uniform(0.8, 1.2) / 5 * 5
            expected = level * annual * weekly[dow] * trend * holiday

            planned_lift = np.ones(n)
            true_lift = np.ones(n)
            for p in promotions:
                if p["sku_id"] != sku_id or p["region"] != region:
                    continue
                mask = (dates.date >= p["start_date"]) & (dates.date <= p["end_date"])
                lift = 1.1 * p["discount_percentage"] / 100
                planned_lift[mask] *= 1 + lift * (1 + rng.normal(0, 0.05))
                mult = 1.0
                for sc in S.SCENARIOS:
                    if sc["region"] == region:
                        mult = sc.get("promo_true_lift_multiplier", {}).get(sku_id, mult)
                true_lift[mask] *= 1 + lift * mult * (1 + rng.normal(0, 0.08))

            scenario_effect = np.ones(n)
            coverage_cap = np.full(n, np.inf)
            for sc in S.SCENARIOS:
                if sc["region"] != region:
                    continue
                for e in sc.get("demand_effects", []):
                    if e["sku_id"] == sku_id:
                        mask = (dates.date >= e["start"]) & (dates.date <= e["end"])
                        scenario_effect[mask] *= 1 + e["effect"]
                for e in sc.get("supply_effects", []):
                    if e["sku_id"] == sku_id:
                        mask = (dates.date >= e["start"]) & (dates.date <= e["end"])
                        coverage_cap[mask] = np.minimum(
                            coverage_cap[mask], e["coverage"] * (1 + rng.normal(0, 0.04, mask.sum()))
                        )

            bias = rng.normal(1.0, 0.015)
            forecast = expected * planned_lift * bias * np.exp(rng.normal(0, 0.03, n))
            true_demand = expected * true_lift * scenario_effect * np.exp(rng.normal(0, 0.055, n))

            # Replenishment is planned against the forecast, not against (unobserved) true demand
            inventory = forecast * rng.uniform(1.5, 3.2, n)
            rare = rng.random(n) < 0.003  # occasional single-day local stockouts (realism)
            inventory[rare] = true_demand[rare] * rng.uniform(0.85, 0.97, rare.sum())
            inventory = np.round(np.minimum(inventory, true_demand * coverage_cap))
            sales = np.minimum(np.round(true_demand), inventory)
            stockout = true_demand > inventory

            for i in range(n):
                demand_rows.append({
                    "date": date_list[i], "sku_id": sku_id, "product_name": name, "category": category,
                    "brand": S.BRAND, "region": region,
                    "forecast_quantity": int(round(forecast[i])), "actual_sales_quantity": int(sales[i]),
                })
                inventory_rows.append({
                    "date": date_list[i], "sku_id": sku_id, "region": region,
                    "available_inventory": int(inventory[i]), "stockout_flag": bool(stockout[i]),
                })

    ext_rows = ext_bg + [dict(e) for e in S.SCENARIO_EXTERNAL_EVENTS]
    ops_rows = ops_bg + [dict(e) for e in S.SCENARIO_OPERATIONAL_EVENTS]

    ground_truth = {
        "seed": seed,
        "note": "Hidden labels for evaluation only. Never loaded by the investigation engine.",
        "scenarios": [
            {
                "scenario_id": sc["scenario_id"], "name": sc["name"], "region": sc["region"],
                "start": sc["window"][0].isoformat(), "end": sc["window"][1].isoformat(),
                "direction": sc["direction"], "affected_skus": sc["affected_skus"],
                "primary_event_ids": sc["primary_event_ids"], "acceptable_drivers": sc["acceptable_drivers"],
                "confounders": sc["confounders"], "expected_outcome": sc["expected_outcome"],
            }
            for sc in S.SCENARIOS
        ],
    }

    return SyntheticDataset(
        demand=pd.DataFrame(demand_rows),
        inventory=pd.DataFrame(inventory_rows),
        promotions=pd.DataFrame(promotions),
        operational_events=pd.DataFrame(ops_rows),
        external_events=pd.DataFrame(ext_rows),
        ground_truth=ground_truth,
    )


def write_dataset(ds: SyntheticDataset, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in ds.frames().items():
        p = out_dir / f"{name}.csv"
        df.to_csv(p, index=False)
        paths[name] = p
    gt = out_dir / "ground_truth.json"
    gt.write_text(json.dumps(ds.ground_truth, indent=2), encoding="utf-8")
    paths["ground_truth"] = gt
    return paths


if __name__ == "__main__":  # python -m backend.synthetic_data.generator
    from backend.app.config import SYNTHETIC_OUTPUT_DIR

    written = write_dataset(generate(), SYNTHETIC_OUTPUT_DIR)
    for k, v in written.items():
        print(f"{k:20s} {v}")
