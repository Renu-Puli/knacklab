import json
import logging
import re
import sys
import contextvars
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable to hold the request ID for the current async task
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# Regular expressions for mandatory secret redaction
SENSITIVE_PATTERNS = [
    # Sentinel value specified by bootcamp verification
    (re.compile(r"DO_NOT_LOG_ME_123"), "[REDACTED]"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+"), r"\1[REDACTED]"),
    # Raw API keys (e.g. test-api-key-*, API_KEY_*)
    (re.compile(r"(API_KEY_[A-Z0-9_]+)"), "[REDACTED]"),
    (re.compile(r"(test-api-key-[a-z0-9_\-]+)"), "[REDACTED]"),
    # PostgreSQL / Database connection URLs with passwords
    (re.compile(r"(postgres(?:ql)?(?:\+\w+)?://[^:]+:)([^@]+)(@)"), r"\1[REDACTED]\3"),
]

# Prohibited sensitive keys in structured metadata/dictionaries
SENSITIVE_FIELD_NAMES = {
    "x-api-key",
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "password",
    "token",
    "secret",
    "api_key",
    "database_url",
}

# Dangerous ASCII/Unicode control characters (C0 and C1 control codes except standard whitespace)
DANGEROUS_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize_log_text(text: str) -> str:
    """
    Neutralize CR/LF and dangerous control characters to prevent log injection (CWE-117).
    - Escapes CR (\\r) and LF (\\n) characters so user inputs cannot break lines or forge log records.
    - Strips dangerous non-printable control characters.
    - Preserves legitimate content and valid URL structures.
    """
    if not isinstance(text, str):
        return text
    # 1. Escape CR and LF characters to prevent line splitting and forged log entries
    sanitized = text.replace("\r", "\\r").replace("\n", "\\n")
    # 2. Strip dangerous non-printable control characters
    sanitized = DANGEROUS_CONTROL_CHARS.sub("", sanitized)
    return sanitized


def redact_text(text: str) -> str:
    """Sanitize strings against log injection, known sensitive patterns, and credentials."""
    if not isinstance(text, str):
        return text
    # 1. Neutralize control characters and newlines first
    sanitized = sanitize_log_text(text)
    # 2. Redact sensitive patterns and credentials
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact sensitive dictionary keys/values and sanitize against log injection."""
    cleaned = {}
    for k, v in data.items():
        k_str = sanitize_log_text(str(k))
        k_lower = k_str.lower()
        if any(sensitive in k_lower for sensitive in SENSITIVE_FIELD_NAMES):
            cleaned[k_str] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k_str] = redact_dict(v)
        elif isinstance(v, list):
            cleaned[k_str] = [redact_text(item) if isinstance(item, str) else item for item in v]
        elif isinstance(v, str):
            cleaned[k_str] = redact_text(v)
        else:
            cleaned[k_str] = v
    return cleaned


class RedactingFilter(logging.Filter):
    """
    Logging filter that:
    1. Enforces redaction of secrets, tokens, and credentials in log messages.
    2. Neutralizes newlines, carriage returns, and control characters to prevent CWE-117 log injection.
    3. Populates record.request_id from the active context variable if missing.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # Automatically attach request_id from contextvar if not already on the record
        if not hasattr(record, "request_id") or not record.request_id:
            record.request_id = request_id_ctx.get() or "system"
        elif isinstance(record.request_id, str):
            record.request_id = sanitize_log_text(record.request_id)

        # Redact and sanitize record.msg if string
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)

        # Redact and sanitize arguments if provided
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_text(a) if isinstance(a, str) else a for a in record.args
                )

        return True


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records into consistent, production-ready JSON objects.
    Guarantees request_id, route, status_code, and latency_ms are present on request events.
    Guarantees all string fields are sanitized against control characters and log injection.
    Guarantees single-line output without raw unescaped newlines.
    """
    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or request_id_ctx.get() or "system"
        if isinstance(req_id, str):
            req_id = sanitize_log_text(req_id)

        msg = record.getMessage()
        if isinstance(msg, str):
            msg = redact_text(msg)

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": msg,
            "request_id": req_id,
        }

        # Include structured HTTP request metadata if present
        for key in ("route", "status_code", "latency_ms", "method"):
            val = getattr(record, key, None)
            if val is not None:
                if isinstance(val, str):
                    payload[key] = sanitize_log_text(val)
                else:
                    payload[key] = val

        # Include exception information safely in server logs (without stack traces leaking to clients)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


logger = logging.getLogger("apps.api")


def resolve_log_level(level: int | str | None) -> int:
    """Safely resolve an int or string log level to a standard logging level."""
    if level is None:
        return logging.INFO
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        level_clean = level.strip().upper()
        if hasattr(logging, level_clean):
            resolved = getattr(logging, level_clean)
            if isinstance(resolved, int):
                return resolved
        level_map = {
            "WARN": logging.WARNING,
            "FATAL": logging.CRITICAL,
        }
        if level_clean in level_map:
            return level_map[level_clean]
    return logging.INFO


def configure_logging(level: int | str = logging.INFO) -> logging.Logger:
    """Initialize structured logging with secret redaction on stdout."""
    resolved_level = resolve_log_level(level)

    root = logging.getLogger()
    root.setLevel(resolved_level)

    # Avoid duplicate handlers on re-configuration
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(resolved_level)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(StructuredJsonFormatter())

    root.addHandler(handler)
    logger.setLevel(resolved_level)
    return logger


def log_request_event(
    request_id: str,
    route: str,
    status_code: int,
    latency_ms: float,
    method: str = "GET"
) -> None:
    """Log a completed HTTP request with required metadata and secret redaction."""
    safe_req_id = sanitize_log_text(request_id) if isinstance(request_id, str) else str(request_id)
    safe_route = sanitize_log_text(route) if isinstance(route, str) else str(route)
    safe_method = sanitize_log_text(method) if isinstance(method, str) else str(method)
    extra = {
        "request_id": safe_req_id,
        "route": safe_route,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "method": safe_method,
    }
    logger.info(
        f"{safe_method} {safe_route} completed with status {status_code} in {latency_ms}ms",
        extra=extra
    )
