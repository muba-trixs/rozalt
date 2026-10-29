"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config import get_settings
from backend.schemas.common import ApiError, error_response, ok

logger = logging.getLogger("demand_intel")
settings = get_settings()

app = FastAPI(title="Rozalt API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, exc: StarletteHTTPException):
    return error_response(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    return error_response(422, "validation_error", "Request validation failed", exc.errors())


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception):  # pragma: no cover - defensive
    logger.exception("Unhandled error")
    return error_response(500, "internal_error", f"{type(exc).__name__}: {exc}")


from backend.api import analytics, anomalies, datasets, events, investigations  # noqa: E402
from backend.api import settings as settings_api  # noqa: E402

for _r in (datasets.router, analytics.router, anomalies.router, events.router, investigations.router,
           settings_api.router):
    app.include_router(_r)


@app.get("/api/v1/health")
def health():
    return ok({"status": "ok", "llm_available": settings.llm_available, "model": settings.llm_model})
