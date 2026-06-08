from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, RequestResponseEndpoint

from app.core.exceptions import AppError, build_error_response
from app.core.logging import get_logger


logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return structured JSON responses."""

    def __init__(self, app: ASGIApp, logger_: logging.Logger | None = None) -> None:
        super().__init__(app)
        self._logger = logger_ or logging.getLogger("cinema-event-system.errors")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except HTTPException as exc:
            error_response = build_error_response(
                code="http_exception",
                message=str(exc.detail),
                path=str(request.url.path),
                details={"headers": dict(exc.headers or {})},
            )
            return JSONResponse(status_code=exc.status_code, content=error_response.model_dump())
        except AppError as exc:
            logger.exception("Application error on %s", request.url.path)
            error_response = build_error_response(
                code=exc.code,
                message=exc.message,
                path=str(request.url.path),
                details=exc.details,
            )
            return JSONResponse(status_code=exc.status_code, content=error_response.model_dump())
        except Exception:
            self._logger.exception("Unhandled exception on %s", request.url.path)
            error_response = build_error_response(
                code="internal_server_error",
                message="An unexpected error occurred.",
                path=str(request.url.path),
            )
            return JSONResponse(status_code=500, content=error_response.model_dump())
