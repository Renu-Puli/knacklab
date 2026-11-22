import os
import sys
import json
import logging
import io

# Add apps/api to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from app.config import Settings, settings
from app.logging_config import configure_logging, resolve_log_level, logger, StructuredJsonFormatter, RedactingFilter
from app.main import app
from starlette.testclient import TestClient

def test_level_resolution():
    print("=== 1. Level Resolution Unit Tests ===")
    assert resolve_log_level("INFO") == logging.INFO
    assert resolve_log_level("info") == logging.INFO
    assert resolve_log_level("DEBUG") == logging.DEBUG
    assert resolve_log_level("debug") == logging.DEBUG
    assert resolve_log_level("WARNING") == logging.WARNING
    assert resolve_log_level("warning") == logging.WARNING
    assert resolve_log_level("WARN") == logging.WARNING
    assert resolve_log_level("warn") == logging.WARNING
    assert resolve_log_level("ERROR") == logging.ERROR
    assert resolve_log_level("CRITICAL") == logging.CRITICAL
    assert resolve_log_level("FATAL") == logging.CRITICAL
    assert resolve_log_level("INVALID_CUSTOM_XYZ") == logging.INFO
    assert resolve_log_level(None) == logging.INFO
    assert resolve_log_level(logging.DEBUG) == logging.DEBUG
    print("[PASS] All string/int/invalid resolve_log_level cases verified.")

def test_settings_loading():
    print("\n=== 2. Settings LOG_LEVEL Loading ===")
    s = Settings()
    print(f"Loaded Settings.log_level: '{s.log_level}'")
    assert s.log_level.upper() == "INFO"
    print("[PASS] Settings loaded LOG_LEVEL from .env successfully.")

def test_stream_level_filtering():
    print("\n=== 3. Stream Handler Level Filtering Tests ===")
    
    def capture_logs_at(level_input):
        buf = io.StringIO()
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        handler = logging.StreamHandler(buf)
        resolved = resolve_log_level(level_input)
        root.setLevel(resolved)
        handler.setLevel(resolved)
        handler.addFilter(RedactingFilter())
        handler.setFormatter(StructuredJsonFormatter())
        root.addHandler(handler)
        logger.setLevel(resolved)

        logger.debug("Test DEBUG marker")
        logger.info("Test INFO marker")
        logger.warning("Test WARNING marker")
        logger.error("Test ERROR marker")

        for h in list(root.handlers):
            root.removeHandler(h)
        return buf.getvalue()

    # Case A: INFO
    out_info = capture_logs_at("INFO")
    assert "Test DEBUG marker" not in out_info, "DEBUG should be suppressed at INFO"
    assert "Test INFO marker" in out_info, "INFO should be emitted at INFO"
    assert "Test WARNING marker" in out_info, "WARNING should be emitted at INFO"
    assert "Test ERROR marker" in out_info, "ERROR should be emitted at INFO"
    print("[PASS] LOG_LEVEL=INFO emits INFO, WARN, ERROR and suppresses DEBUG.")

    # Case B: DEBUG
    out_debug = capture_logs_at("DEBUG")
    assert "Test DEBUG marker" in out_debug, "DEBUG should be emitted at DEBUG"
    assert "Test INFO marker" in out_debug, "INFO should be emitted at DEBUG"
    print("[PASS] LOG_LEVEL=DEBUG emits DEBUG and INFO.")

    # Case C: WARNING
    out_warn = capture_logs_at("WARNING")
    assert "Test DEBUG marker" not in out_warn, "DEBUG should be suppressed at WARNING"
    assert "Test INFO marker" not in out_warn, "INFO should be suppressed at WARNING"
    assert "Test WARNING marker" in out_warn, "WARNING should be emitted at WARNING"
    assert "Test ERROR marker" in out_warn, "ERROR should be emitted at WARNING"
    print("[PASS] LOG_LEVEL=WARNING suppresses INFO/DEBUG while preserving WARN/ERROR.")

    # Case D: Invalid string fallback
    out_invalid = capture_logs_at("INVALID_VALUE")
    assert "Test INFO marker" in out_invalid, "Invalid level should safely fallback to INFO"
    assert "Test DEBUG marker" not in out_invalid, "DEBUG should be suppressed under fallback INFO"
    print("[PASS] Invalid LOG_LEVEL safely falls back to INFO.")

def test_http_request_flow():
    print("\n=== 4. HTTP Request Lifecycle Flow Under LOG_LEVEL=INFO ===")
    configure_logging("INFO")
    client = TestClient(app)

    # 1. Create link
    resp_create = client.post(
        "/links",
        json={"long_url": "https://example.com/log-verification", "tags": ["logging"]},
        headers={"X-API-Key": "test-api-key-org-a", "X-Tenant-ID": "test_tenant"}
    )
    print(f"POST /links Response: {resp_create.status_code}")
    assert resp_create.status_code == 201
    code = resp_create.json()["code"]

    # 2. Redirect
    resp_redirect = client.get(f"/r/{code}", follow_redirects=False)
    print(f"GET /r/{code} Response: {resp_redirect.status_code}")
    assert resp_redirect.status_code in (302, 307)
    assert resp_redirect.headers.get("location") == "https://example.com/log-verification"

    # 3. Nonexistent link
    resp_404 = client.get("/r/nonexistent_xyz_404", follow_redirects=False)
    print(f"GET /r/nonexistent_xyz_404 Response: {resp_404.status_code}")
    assert resp_404.status_code == 404

    print("[PASS] All request endpoints function correctly with expected status codes.")

if __name__ == "__main__":
    test_level_resolution()
    test_settings_loading()
    test_stream_level_filtering()
    test_http_request_flow()
    print("\n=======================================================")
    print("=== ALL BUG #3 VERIFICATION & FILTERING TESTS PASSED ===")
    print("=======================================================")
