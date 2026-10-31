"""Exception handlers producing the standard error envelope from the API contract.

Envelope shape::

    {"detail": "...", "error_code": "...", "timestamp": "2026-10-24T12:00:00Z"}
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import RescuePayError

logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "RATE_LIMITED",
}


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def error_response(
    status_code: int,
    detail: Any,
    error_code: str,
    *,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a JSON error response using the standard envelope."""
    body: dict[str, Any] = {
        "detail": detail,
        "error_code": error_code,
        "timestamp": _timestamp(),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body)


async def rescuepay_error_handler(
    request: Request, exc: RescuePayError
) -> JSONResponse:
    """Map domain exceptions to their declared status and error code."""
    if exc.status_code >= 500:
        logger.error(
            "request.failed",
            extra={
                "error_code": exc.error_code,
                "path": request.url.path,
                "paypal_debug_id": exc.debug_id,
            },
        )
    extra = {"paypal_debug_id": exc.debug_id} if exc.debug_id else None
    return error_response(exc.status_code, exc.detail, exc.error_code, extra=extra)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wrap framework HTTP errors (404, 405, ...) in the standard envelope."""
    code = _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, exc.detail, code)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return schema validation failures (422) in the standard envelope."""
    # Pydantic validator context can contain a ValueError object, which cannot
    # be JSON-encoded directly. Do not echo arbitrary input or exception objects.
    errors = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return error_response(422, errors, "REQUEST_VALIDATION_ERROR")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: log the traceback, return a sanitized 500."""
    logger.exception("request.unhandled_exception", extra={"path": request.url.path})
    return error_response(500, "An internal error occurred.", "INTERNAL_ERROR")


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all handlers to the application."""
    app.add_exception_handler(RescuePayError, rescuepay_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
