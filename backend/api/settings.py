"""Configuration endpoints: detection thresholds, heuristic relevance weights, LLM status."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.database.session import get_db
from backend.schemas.common import ApiError, ok
from backend.services import settings_service as svc

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _payload(db: Session) -> dict:
    s = get_settings()
    rel = svc.get_relevance_config(db)
    return {
        "detection": svc.get_detection_config(db),
        "detection_defaults": svc.DETECTION_DEFAULTS,
        "relevance": rel,
        "llm": {"configured": bool(s.anthropic_api_key.strip()), "enabled": s.llm_enabled,
                "available": s.llm_available, "provider": "anthropic", "model": s.llm_model, "effort": s.llm_effort},
    }


@router.get("")
def get_all(db: Session = Depends(get_db)):
    return ok(_payload(db))


@router.put("/detection")
def put_detection(values: dict[str, float], db: Session = Depends(get_db)):
    try:
        svc.update_detection_config(db, values)
    except ValueError as exc:
        raise ApiError(400, "invalid_settings", str(exc))
    return ok(_payload(db))


@router.put("/relevance/weights")
def put_weights(weights: dict[str, float], db: Session = Depends(get_db)):
    try:
        svc.update_relevance_weights(db, weights)
    except ValueError as exc:
        raise ApiError(400, "invalid_settings", str(exc))
    return ok(_payload(db))


@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    svc.reset_settings(db)
    return ok(_payload(db))
