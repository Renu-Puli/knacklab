import re
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.logging_config import request_id_ctx, log_request_event

# Only allow safe alphanumeric, hyphens, and underscores up to 64 chars
REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def generate_safe_request_id() -> str:
    """Generate a safe, collision-resistant unique request identifier."""
    return f"req_{uuid.uuid4().hex}"


def validate_or_create_request_id(incoming: str | None) -> str:
    """
    Validate client-supplied request ID.
    Rejects malformed, empty, or oversized values to prevent header injection.
    """
    if incoming:
        trimmed = incoming.strip()
        if REQUEST_ID_PATTERN.match(trimmed):
            return trimmed
    return generate_safe_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Extracts or safely generates a correlation Request ID.
    2. Makes request_id available via request.state and contextvars.
    3. Adds X-Request-ID header to every response (success and error).
    4. Measures precise execution latency in milliseconds.
    5. Logs structured request audit events with secret redaction.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        raw_header = request.headers.get("X-Request-ID")
        req_id = validate_or_create_request_id(raw_header)

        # Store in request state for access in route handlers and exception handlers
        request.state.request_id = req_id

        # Bind to contextvar for thread/task-local logging correlation
        token = request_id_ctx.set(req_id)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # If an unhandled exception bubbles up through ASGI middleware
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_request_event(
                request_id=req_id,
                route=request.url.path,
                status_code=500,
                latency_ms=latency_ms,
                method=request.method,
            )
            raise
        finally:
            request_id_ctx.reset(token)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Ensure X-Request-ID is attached to every outgoing response header
        response.headers["X-Request-ID"] = req_id

        # Log structured request completion event
        log_request_event(
            request_id=req_id,
            route=request.url.path,
            status_code=response.status_code,
            latency_ms=latency_ms,
            method=request.method,
        )

        return response
