"""Data ingestion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import models as M
from backend.database.session import get_db
from backend.schemas.common import ApiError, ok
from backend.services import ingestion_service as ingest
from backend.services.anomaly_detection import run_detection
from backend.services.demand_analytics import data_date_range
from backend.services.synthetic_loader import load_synthetic

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _check_type(dataset_type: str) -> None:
    if dataset_type not in ingest.SPECS:
        raise ApiError(404, "unknown_dataset_type",
                       f"Unknown dataset type '{dataset_type}'. Expected one of: {', '.join(ingest.SPECS)}")


async def _read(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file_too_large", "File exceeds 50 MB limit")
    if not content.strip():
        raise ApiError(400, "empty_file", "Uploaded file is empty")
    return content


@router.get("/specs")
def specs():
    return ok({k: {"required": s.required, "optional": s.optional, "description": s.description,
                   "key": s.key, "order": ingest.IMPORT_ORDER.index(k)} for k, s in ingest.SPECS.items()})


@router.get("/template/{dataset_type}", response_class=PlainTextResponse)
def template(dataset_type: str):
    _check_type(dataset_type)
    s = ingest.SPECS[dataset_type]
    return PlainTextResponse(",".join(s.required + s.optional) + "\n", media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{dataset_type}_template.csv"'})


@router.post("/{dataset_type}/preview")
async def preview(dataset_type: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _check_type(dataset_type)
    content = await _read(file)
    try:
        df = ingest.read_csv_bytes(content)
    except Exception as exc:
        raise ApiError(400, "invalid_csv", f"Could not parse CSV: {exc}")
    result = ingest.validate_frame(db, dataset_type, df)
    return ok({**result.summary(), "filename": file.filename})


@router.post("/{dataset_type}/import")
async def import_dataset(dataset_type: str, file: UploadFile = File(...), detect: bool = Query(True),
                         db: Session = Depends(get_db)):
    _check_type(dataset_type)
    content = await _read(file)
    res = ingest.import_csv_bytes(db, dataset_type, content, file.filename or "upload.csv")
    if dataset_type == "demand" and detect and res.get("rows_imported"):
        res["detection"] = {k: v for k, v in run_detection(db).items() if k != "config"}
    return ok(res)


@router.get("/imports")
def imports(db: Session = Depends(get_db)):
    rows = db.scalars(select(M.DatasetImport).order_by(M.DatasetImport.id.desc()).limit(100)).all()
    return ok([{"id": r.id, "dataset_type": r.dataset_type, "filename": r.filename, "status": r.status,
                "rows_total": r.rows_total, "rows_imported": r.rows_imported, "rows_rejected": r.rows_rejected,
                "rows_duplicate": r.rows_duplicate, "errors": (r.errors or [])[:20],
                "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows])


@router.post("/load-synthetic")
def synthetic(seed: int = Query(42), db: Session = Depends(get_db)):
    return ok(load_synthetic(db, seed))


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    def n(model) -> int:
        return db.scalar(select(func.count()).select_from(model))

    counts = {
        "products": n(M.Product), "regions": n(M.Region), "demand_records": n(M.DemandRecord),
        "inventory_records": n(M.InventoryRecord), "promotions": n(M.Promotion),
        "operational_events": n(M.OperationalEvent), "external_events": n(M.ExternalEvent),
        "anomalies": n(M.Anomaly), "investigations": n(M.Investigation),
    }
    lo, hi = data_date_range(db)
    return ok({"counts": counts, "date_range": [lo.isoformat() if lo else None, hi.isoformat() if hi else None]})
