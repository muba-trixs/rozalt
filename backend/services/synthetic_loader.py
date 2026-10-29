"""Load the deterministic synthetic dataset through the same ingestion path as user uploads."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.config import SYNTHETIC_OUTPUT_DIR
from backend.services import ingestion_service as ingest
from backend.services.anomaly_detection import run_detection
from backend.synthetic_data.generator import generate, write_dataset


def load_synthetic(db: Session, seed: int = 42) -> dict:
    ds = generate(seed)
    paths = write_dataset(ds, SYNTHETIC_OUTPUT_DIR)
    ingest.clear_all_data(db)
    imports = []
    for t in ingest.IMPORT_ORDER:
        content = paths[t].read_bytes()
        res = ingest.import_csv_bytes(db, t, content, f"synthetic/{paths[t].name}")
        imports.append({k: res.get(k) for k in ("dataset_type", "status", "rows_total", "rows_imported",
                                                 "rows_rejected", "import_id")})
    detection = run_detection(db)
    return {"seed": seed, "imports": imports, "anomalies_detected": detection["created"]}
