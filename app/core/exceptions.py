from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    path: str | None = None


class AppError(Exception):
    """Base application exception for future domain and infrastructure errors."""

    status_code = 500
    code = "internal_server_error"

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class DatabaseUnavailableError(AppError):
    status_code = 503
    code = "database_unavailable"


def build_error_response(
    *,
    code: str,
    message: str,
    path: str | None = None,
    details: Any | None = None,
) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details),
        path=path,
    )
