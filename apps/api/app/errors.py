import logging
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.logging_config import request_id_ctx

logger = logging.getLogger("apps.api.errors")

# Standard HTTP status code to stable application error code mapping
STATUS_CODE_MAP: Dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    410: "GONE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}


def make_error_envelope(code: str, message: str, request_id: str) -> Dict[str, Any]:
    """
    Construct the consistent, production-safe error response envelope.
    Guarantees no stack traces, raw SQL, or secrets are exposed.
    """
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }


def _get_request_id(request: Request) -> str:
    """Safely resolve request_id from request.state or contextvar."""
    return getattr(request.state, "request_id", None) or request_id_ctx.get() or "unknown"


def format_validation_error(exc: RequestValidationError) -> str:
    """
    Transform Pydantic validation errors into clean, safe, human-readable messages.
    Never exposes internal models, code paths, or private data.
    """
    field_messages = []
    for err in exc.errors():
        loc_parts = [str(part) for part in err.get("loc", []) if part != "body"]
        loc_str = ".".join(loc_parts)
        msg = err.get("msg", "Invalid value")
        # Clean up Pydantic prefix noise if present
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        if loc_str:
            field_messages.append(f"{loc_str}: {msg}")
        else:
            field_messages.append(msg)

    if field_messages:
        return "Validation failed: " + "; ".join(field_messages)
    return "Invalid request payload"


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers with standard error envelope."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = _get_request_id(request)
        status_code = exc.status_code

        # 5xx responses represent server mistakes - must be generic and safe
        if status_code >= 500:
            code = "INTERNAL_ERROR"
            message = "Internal server error"
            logger.error(
                f"HTTP {status_code} server error: {exc.detail}",
                extra={"request_id": request_id, "route": request.url.path, "status_code": status_code},
                exc_info=True,
            )
        else:
            code = STATUS_CODE_MAP.get(status_code, "CLIENT_ERROR")
            message = str(exc.detail) if exc.detail else "Client request error"

        headers = dict(exc.headers or {})
        headers["X-Request-ID"] = request_id

        return JSONResponse(
            status_code=status_code,
            content=make_error_envelope(code=code, message=message, request_id=request_id),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = _get_request_id(request)
        safe_message = format_validation_error(exc)

        headers = {"X-Request-ID": request_id}

        return JSONResponse(
            status_code=422,
            content=make_error_envelope(
                code="VALIDATION_ERROR",
                message=safe_message,
                request_id=request_id,
            ),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _get_request_id(request)

        # Log complete diagnostic exception traceback server-side only
        logger.error(
            f"Unhandled server exception on {request.method} {request.url.path}: {exc}",
            extra={"request_id": request_id, "route": request.url.path, "status_code": 500},
            exc_info=True,
        )

        headers = {"X-Request-ID": request_id}

        # Return sanitized, opaque 500 response without stack traces or credentials
        return JSONResponse(
            status_code=500,
            content=make_error_envelope(
                code="INTERNAL_ERROR",
                message="Internal server error",
                request_id=request_id,
            ),
            headers=headers,
        )
