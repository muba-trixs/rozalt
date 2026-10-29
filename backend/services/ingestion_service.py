"""CSV ingestion: schema validation, normalisation, duplicate handling and persistence."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from backend import models as M

DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y", "%b %d %Y", "%Y-%m-%dT%H:%M:%S"]
TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f"}
MAX_REPORTED_ERRORS = 200


@dataclass(frozen=True)
class DatasetSpec:
    required: list[str]
    optional: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    numeric: list[str] = field(default_factory=list)
    booleans: list[str] = field(default_factory=list)
    key: list[str] = field(default_factory=list)
    needs_known_sku: bool = False
    description: str = ""


SPECS: dict[str, DatasetSpec] = {
    "demand": DatasetSpec(
        required=["date", "sku_id", "product_name", "region", "forecast_quantity", "actual_sales_quantity"],
        optional=["category", "brand"],
        dates=["date"], numeric=["forecast_quantity", "actual_sales_quantity"],
        key=["date", "sku_id", "region"],
        description="Daily forecast and recorded sales per SKU and region",
    ),
    "inventory": DatasetSpec(
        required=["date", "sku_id", "region", "available_inventory", "stockout_flag"],
        dates=["date"], numeric=["available_inventory"], booleans=["stockout_flag"],
        key=["date", "sku_id", "region"], needs_known_sku=True,
        description="Daily available inventory and stockout flags",
    ),
    "promotions": DatasetSpec(
        required=["start_date", "end_date", "sku_id", "region", "promotion_type", "discount_percentage"],
        dates=["start_date", "end_date"], numeric=["discount_percentage"],
        key=["start_date", "sku_id", "region", "promotion_type"], needs_known_sku=True,
        description="Internal promotions calendar",
    ),
    "operational_events": DatasetSpec(
        required=["event_id", "date", "event_type", "region", "affected_facility", "description"],
        optional=["end_date", "related_sku_ids", "related_category", "severity"],
        dates=["date", "end_date"], key=["event_id"],
        description="Internal operational events (logistics, facilities, quality)",
    ),
    "external_events": DatasetSpec(
        required=["event_id", "event_date", "event_title", "event_description", "event_category", "region",
                  "source", "source_url"],
        optional=["end_date", "related_sku_ids", "related_category", "severity"],
        dates=["event_date", "end_date"], key=["event_id"],
        description="External market, competitor, cultural and weather events",
    ),
}

IMPORT_ORDER = ["demand", "inventory", "promotions", "operational_events", "external_events"]


@dataclass
class ValidationResult:
    dataset_type: str
    columns: list[str]
    missing_columns: list[str]
    unexpected_columns: list[str]
    rows_total: int
    valid: pd.DataFrame
    errors: list[dict]
    rows_rejected: int
    rows_duplicate_in_file: int
    fatal: str | None = None

    def preview(self, n: int = 10) -> list[dict]:
        if self.valid.empty:
            return []
        return _jsonable(self.valid.head(n))

    def summary(self) -> dict[str, Any]:
        return {
            "dataset_type": self.dataset_type,
            "columns": self.columns,
            "missing_columns": self.missing_columns,
            "unexpected_columns": self.unexpected_columns,
            "rows_total": self.rows_total,
            "rows_valid": int(len(self.valid)),
            "rows_rejected": self.rows_rejected,
            "rows_duplicate_in_file": self.rows_duplicate_in_file,
            "errors": self.errors[:MAX_REPORTED_ERRORS],
            "errors_truncated": len(self.errors) > MAX_REPORTED_ERRORS,
            "fatal": self.fatal,
            "preview": self.preview(),
        }


def _jsonable(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    return out.replace({np.nan: None}).to_dict(orient="records")


def _parse_dates(col: pd.Series) -> pd.Series:
    raw = col.astype("string").str.strip()
    result = pd.Series(pd.NaT, index=col.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        missing = result.isna() & raw.notna() & (raw != "")
        if not missing.any():
            break
        result.loc[missing] = pd.to_datetime(raw[missing], format=fmt, errors="coerce")
    return result


def read_csv_bytes(content: bytes) -> pd.DataFrame:
    text = content.decode("utf-8-sig", errors="replace")
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, skip_blank_lines=True)


def _canonical_regions(db: Session, values: pd.Series) -> pd.Series:
    """Map region spellings case-insensitively onto existing regions, or onto one spelling per file."""
    known = {r.lower(): r for r in db.scalars(select(M.Region.region_id))}
    cleaned = values.map(lambda v: " ".join(str(v).split()))
    for v in cleaned.unique():
        key = v.lower()
        if key in known:
            continue
        variants = [x for x in cleaned[cleaned.str.lower() == key].unique()]
        mixed = [x for x in variants if x != x.lower()]
        known[key] = mixed[0] if mixed else v.title()
    return cleaned.map(lambda v: known[v.lower()])


def validate_frame(db: Session, dataset_type: str, df: pd.DataFrame) -> ValidationResult:
    if dataset_type not in SPECS:
        raise ValueError(f"Unknown dataset type '{dataset_type}'")
    spec = SPECS[dataset_type]
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    columns = list(df.columns)
    missing = [c for c in spec.required if c not in columns]
    unexpected = [c for c in columns if c not in spec.required + spec.optional]
    empty = pd.DataFrame()
    if missing:
        return ValidationResult(dataset_type, columns, missing, unexpected, len(df), empty, [], len(df), 0,
                                fatal=f"Missing required columns: {', '.join(missing)}")
    if df.empty:
        return ValidationResult(dataset_type, columns, [], unexpected, 0, empty, [], 0, 0, fatal="File contains no rows")

    df = df[[c for c in columns if c in spec.required + spec.optional]]
    for c in spec.optional:
        if c not in df.columns:
            df[c] = ""
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    raw = df.copy()
    errors: list[dict] = []
    bad = pd.Series(False, index=df.index)

    def flag(mask: pd.Series, column: str, message: str) -> None:
        nonlocal bad
        for idx in df.index[mask & ~bad][: MAX_REPORTED_ERRORS]:
            errors.append({"row": int(idx) + 2, "column": column, "value": str(raw.at[idx, column]),
                           "message": message})
        bad = bad | mask

    for c in spec.required:
        flag(df[c] == "", c, "Required value is empty")

    parsed_dates: dict[str, pd.Series] = {}
    for c in spec.dates:
        parsed = _parse_dates(df[c])
        parsed_dates[c] = parsed
        present = df[c] != ""
        flag(present & parsed.isna(), c, "Unrecognised date format (expected YYYY-MM-DD)")
        df[c] = parsed.dt.date.where(parsed.notna(), None)

    for c in spec.numeric:
        num = pd.to_numeric(df[c], errors="coerce")
        flag(num.isna() & (df[c] != ""), c, "Value is not numeric")
        flag(num < 0, c, "Value must be non-negative")
        df[c] = num

    for c in spec.booleans:
        low = df[c].str.lower()
        flag(~low.isin(TRUE_VALUES | FALSE_VALUES), c, "Expected a boolean (true/false, 1/0, yes/no)")
        df[c] = low.isin(TRUE_VALUES)

    if dataset_type == "promotions":
        flag(df["discount_percentage"] > 100, "discount_percentage", "Discount must be between 0 and 100")
        flag(parsed_dates["end_date"] < parsed_dates["start_date"], "end_date", "end_date is before start_date")

    df["region"] = _canonical_regions(db, df["region"])

    if dataset_type == "demand":
        df["sku_id"] = df["sku_id"].str.upper()
    elif spec.needs_known_sku:
        df["sku_id"] = df["sku_id"].str.upper()
        known = set(db.scalars(select(M.Product.sku_id)))
        flag(~df["sku_id"].isin(known), "sku_id", "Unknown sku_id — import the demand dataset first")

    valid = df[~bad]
    dup_mask = valid.duplicated(subset=spec.key, keep="first")
    dup_count = int(dup_mask.sum())
    valid = valid[~dup_mask].reset_index(drop=True)

    return ValidationResult(
        dataset_type=dataset_type, columns=columns, missing_columns=[], unexpected_columns=unexpected,
        rows_total=len(df), valid=valid, errors=errors, rows_rejected=int(bad.sum()),
        rows_duplicate_in_file=dup_count,
    )


def _split_ids(v: str) -> list[str]:
    return [s.strip().upper() for s in str(v or "").replace(",", ";").split(";") if s.strip()]


def _blank(v: Any) -> Any:
    return None if v in ("", None) or (isinstance(v, float) and np.isnan(v)) else v


def _existing_keys(db: Session, dataset_type: str, valid: pd.DataFrame) -> set[tuple]:
    if dataset_type == "demand":
        rows = db.execute(select(M.DemandRecord.date, M.DemandRecord.sku_id, M.DemandRecord.region_id))
    elif dataset_type == "inventory":
        rows = db.execute(select(M.InventoryRecord.date, M.InventoryRecord.sku_id, M.InventoryRecord.region_id))
    elif dataset_type == "promotions":
        rows = db.execute(select(M.Promotion.start_date, M.Promotion.sku_id, M.Promotion.region_id,
                                 M.Promotion.promotion_type))
    elif dataset_type == "operational_events":
        rows = db.execute(select(M.OperationalEvent.event_id))
    else:
        rows = db.execute(select(M.ExternalEvent.event_id))
    return {tuple(r) for r in rows}


def persist(db: Session, result: ValidationResult) -> dict[str, int]:
    """Insert validated rows, skipping records whose key already exists in the database."""
    t = result.dataset_type
    spec = SPECS[t]
    valid = result.valid
    if valid.empty:
        return {"imported": 0, "duplicate_in_db": 0}

    existing = _existing_keys(db, t, valid)
    keys = list(valid[spec.key].itertuples(index=False, name=None))
    new_mask = [k not in existing for k in keys]
    rows = valid[new_mask]
    dup_db = len(valid) - len(rows)

    if t == "demand":
        known_regions = set(db.scalars(select(M.Region.region_id)))
        new_regions = sorted(set(rows["region"]) - known_regions)
        if new_regions:
            db.execute(insert(M.Region), [{"region_id": r} for r in new_regions])
        products = rows.drop_duplicates("sku_id")
        known_skus = set(db.scalars(select(M.Product.sku_id)))
        new_products = [
            {"sku_id": r.sku_id, "product_name": r.product_name, "category": _blank(r.category),
             "brand": _blank(r.brand)}
            for r in products.itertuples() if r.sku_id not in known_skus
        ]
        if new_products:
            db.execute(insert(M.Product), new_products)
        records = [
            {"date": r.date, "sku_id": r.sku_id, "region_id": r.region, "forecast_qty": float(r.forecast_quantity),
             "recorded_sales_qty": float(r.actual_sales_quantity)}
            for r in rows.itertuples()
        ]
        model = M.DemandRecord
    elif t == "inventory":
        records = [
            {"date": r.date, "sku_id": r.sku_id, "region_id": r.region,
             "available_inventory": float(r.available_inventory), "stockout_flag": bool(r.stockout_flag)}
            for r in rows.itertuples()
        ]
        model = M.InventoryRecord
    elif t == "promotions":
        known_regions = set(db.scalars(select(M.Region.region_id)))
        new_regions = sorted(set(rows["region"]) - known_regions)
        if new_regions:
            db.execute(insert(M.Region), [{"region_id": r} for r in new_regions])
        records = [
            {"start_date": r.start_date, "end_date": r.end_date, "sku_id": r.sku_id, "region_id": r.region,
             "promotion_type": r.promotion_type, "discount_pct": float(r.discount_percentage)}
            for r in rows.itertuples()
        ]
        model = M.Promotion
    elif t == "operational_events":
        records = [
            {"event_id": r.event_id, "date": r.date, "end_date": _blank(r.end_date) or r.date,
             "event_type": r.event_type.lower(), "region_id": r.region, "affected_facility": _blank(r.affected_facility),
             "description": r.description, "related_sku_ids": _split_ids(r.related_sku_ids),
             "related_category": _blank(r.related_category), "severity": (_blank(r.severity) or None)}
            for r in rows.itertuples()
        ]
        model = M.OperationalEvent
    else:
        records = [
            {"event_id": r.event_id, "event_date": r.event_date, "end_date": _blank(r.end_date) or r.event_date,
             "event_title": r.event_title, "event_description": r.event_description,
             "event_category": r.event_category.lower(), "region_id": r.region, "source": _blank(r.source),
             "source_url": _blank(r.source_url), "related_sku_ids": _split_ids(r.related_sku_ids),
             "related_category": _blank(r.related_category), "severity": (_blank(r.severity) or None)}
            for r in rows.itertuples()
        ]
        model = M.ExternalEvent

    if t == "inventory":
        known_regions = set(db.scalars(select(M.Region.region_id)))
        unknown = [r for r in records if r["region_id"] not in known_regions]
        if unknown:
            db.execute(insert(M.Region), [{"region_id": r} for r in sorted({u["region_id"] for u in unknown})])

    for i in range(0, len(records), 5000):
        db.execute(insert(model), records[i: i + 5000])
    return {"imported": len(records), "duplicate_in_db": dup_db}


def import_dataframe(db: Session, dataset_type: str, df: pd.DataFrame, filename: str) -> dict[str, Any]:
    result = validate_frame(db, dataset_type, df)
    summary = result.summary()
    if result.fatal:
        imported, dup_db, status = 0, 0, "FAILED"
    else:
        counts = persist(db, result)
        imported, dup_db = counts["imported"], counts["duplicate_in_db"]
        status = "SUCCESS" if result.rows_rejected == 0 else ("PARTIAL" if imported else "FAILED")
        if imported == 0 and result.rows_rejected == 0:
            status = "SUCCESS"
    record = M.DatasetImport(
        dataset_type=dataset_type, filename=filename, status=status, rows_total=result.rows_total,
        rows_imported=imported, rows_rejected=result.rows_rejected,
        rows_duplicate=result.rows_duplicate_in_file + dup_db,
        errors=([{"message": result.fatal}] if result.fatal else []) + result.errors[:MAX_REPORTED_ERRORS],
    )
    db.add(record)
    db.commit()
    summary.update({"import_id": record.id, "status": status, "rows_imported": imported,
                    "rows_duplicate_in_db": dup_db})
    return summary


def import_csv_bytes(db: Session, dataset_type: str, content: bytes, filename: str) -> dict[str, Any]:
    try:
        df = read_csv_bytes(content)
    except Exception as exc:  # malformed CSV
        record = M.DatasetImport(dataset_type=dataset_type, filename=filename, status="FAILED",
                                 errors=[{"message": f"Could not parse CSV: {exc}"}])
        db.add(record)
        db.commit()
        return {"dataset_type": dataset_type, "status": "FAILED", "fatal": f"Could not parse CSV: {exc}",
                "import_id": record.id, "rows_imported": 0, "errors": [], "preview": []}
    return import_dataframe(db, dataset_type, df, filename)


def clear_all_data(db: Session) -> None:
    """Remove all imported and derived records (used before reloading the synthetic dataset)."""
    for model in [M.AnalystFeedback, M.HypothesisEvidence, M.Hypothesis, M.EvidenceRecord, M.CandidateDriver,
                  M.Investigation, M.Anomaly, M.InventoryRecord, M.Promotion, M.DemandRecord,
                  M.OperationalEvent, M.ExternalEvent, M.DatasetImport, M.Product, M.Region]:
        db.execute(delete(model))
    db.commit()
