"""Structured API response envelope: {data, meta, error}."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def ok(data: Any, **meta: Any) -> dict:
    return {"data": data, "meta": meta or {}, "error": None}


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "meta": {}, "error": {"code": code, "message": message, "details": details}},
    )
