import io
import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Ensure apps/api is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Link, ClickEvent
from app.rate_limiter import rate_limiter
from app.logging_config import logger as app_logger, RedactingFilter, StructuredJsonFormatter

# Configure TestClient without automatically raising server exceptions so exception handlers execute
client = TestClient(app, raise_server_exceptions=False)


class LogCaptureHandler(logging.Handler):
    """Memory log capture handler for inspecting formatted structured logs."""
    def __init__(self):
        super().__init__()
        self.records = []
        self.formatted_logs = []
        self.addFilter(RedactingFilter())
        self.setFormatter(StructuredJsonFormatter())

    def emit(self, record):
        self.records.append(record)
        formatted = self.format(record)
        self.formatted_logs.append(formatted)


def run_tests():
    print("=" * 75)
    print("MODULE 05 – STEP 3: BUILD VERIFICATION SUITE")
    print("FastAPI Structured Logging, Correlation IDs, and Safe Error Envelopes")
    print("=" * 75)

    log_capture = LogCaptureHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)

    passed_checks = 0
    total_checks = 0

    try:
        # Reset in-memory rate limiter for a fresh test run
        rate_limiter.reset()

        # =====================================================================
        # TEST A: Validation Error Envelope (HTTP 422)
        # =====================================================================
        print("\n--- TEST A: Validation Error Envelope (HTTP 422) ---")
        total_checks += 1
        res_val = client.post(
            "/api/v1/links",
            headers={"X-API-Key": "API_KEY_A"},
            json={"long_url": "not-a-valid-url"}
        )
        print(f"Status: {res_val.status_code}")
        data_val = res_val.json()
        print(f"Response Body: {json.dumps(data_val, indent=2)}")
        print(f"Response Headers X-Request-ID: {res_val.headers.get('X-Request-ID')}")

        assert res_val.status_code == 422, f"Expected 422, got {res_val.status_code}"
        assert "error" in data_val, "Response body must contain 'error' key"
        err = data_val["error"]
        assert err["code"] == "VALIDATION_ERROR", f"Expected code 'VALIDATION_ERROR', got {err.get('code')}"
        assert isinstance(err["message"], str) and len(err["message"]) > 0, "Expected non-empty message"
        assert "request_id" in err and len(err["request_id"]) > 0, "Missing request_id in error envelope"
        assert res_val.headers.get("X-Request-ID") == err["request_id"], "X-Request-ID header must match envelope request_id"
        assert "traceback" not in json.dumps(data_val).lower(), "Validation response must not leak stack traces"
        assert "Traceback (most recent call last)" not in json.dumps(data_val), "Validation response must not leak tracebacks"
        print("[PASS] TEST A: Validation error returned 422 with safe envelope and X-Request-ID")
        passed_checks += 1

        # Also verify backwards-compatible /links route
        total_checks += 1
        res_val_legacy = client.post(
            "/links",
            headers={"X-API-Key": "API_KEY_A"},
            json={"long_url": "http://"}
        )
        assert res_val_legacy.status_code == 422
        assert res_val_legacy.json()["error"]["code"] == "VALIDATION_ERROR"
        print("[PASS] TEST A2: Legacy /links route returns 422 with identical safe envelope")
        passed_checks += 1

        # =====================================================================
        # TEST B: Unhandled Server Error (HTTP 500)
        # =====================================================================
        print("\n--- TEST B: Unhandled Server Error & Stack Trace Protection (HTTP 500) ---")
        total_checks += 1
        test_req_id = "req_test_server_error_500"
        simulated_crash_msg = "Simulated unexpected database failure / connection drop"

        # Safely simulate an unhandled server error during link creation via patch
        with patch("app.routers.links.generate_short_code", side_effect=RuntimeError(simulated_crash_msg)):
            res_500 = client.post(
                "/api/v1/links",
                headers={
                    "X-API-Key": "API_KEY_A",
                    "X-Request-ID": test_req_id,
                },
                json={"long_url": "https://example.com/valid-url"}
            )

        print(f"Status: {res_500.status_code}")
        data_500 = res_500.json()
        print(f"Response Body: {json.dumps(data_500, indent=2)}")
        print(f"Response Headers X-Request-ID: {res_500.headers.get('X-Request-ID')}")

        assert res_500.status_code == 500, f"Expected 500, got {res_500.status_code}"
        assert "error" in data_500, "500 response must contain 'error' envelope"
        err_500 = data_500["error"]
        assert err_500["code"] == "INTERNAL_ERROR", f"Expected code 'INTERNAL_ERROR', got {err_500.get('code')}"
        assert err_500["message"] == "Internal server error", "Message must be generic 'Internal server error'"
        assert err_500["request_id"] == test_req_id, f"Expected request_id {test_req_id}, got {err_500.get('request_id')}"
        assert res_500.headers.get("X-Request-ID") == test_req_id, "X-Request-ID header must match request_id"

        # Ensure NO raw exception text, stack trace, or internal details exist in client response
        raw_500_text = json.dumps(data_500)
        assert simulated_crash_msg not in raw_500_text, "LEAK: Raw exception message exposed to client!"
        assert "RuntimeError" not in raw_500_text, "LEAK: Python exception class exposed to client!"
        assert "Traceback" not in raw_500_text, "LEAK: Python traceback exposed to client!"
        assert "app/routers" not in raw_500_text, "LEAK: File paths exposed to client!"

        # Verify server-side logs recorded the crash with the matching request ID
        matching_logs = [log for log in log_capture.formatted_logs if test_req_id in log]
        assert len(matching_logs) > 0, f"Expected server logs to contain request_id '{test_req_id}'"
        print(f"Matched Server Log Record: {matching_logs[0]}")
        print("[PASS] TEST B: Server error returned generic 500; zero stack traces leaked; logs contain request_id")
        passed_checks += 1

        # =====================================================================
        # TEST C: Mandatory Secret Redaction & Sentinel Value Protection
        # =====================================================================
        print("\n--- TEST C: Secret Redaction (Sentinel: DO_NOT_LOG_ME_123) ---")
        total_checks += 1
        sentinel_key = "DO_NOT_LOG_ME_123"
        sentinel_req_id = "req_sentinel_audit_check"

        # Clear logs before sentinel test
        log_capture.formatted_logs.clear()

        res_sentinel = client.get(
            "/api/v1/links",
            headers={
                "X-API-Key": sentinel_key,
                "X-Request-ID": sentinel_req_id,
            }
        )
        print(f"Status: {res_sentinel.status_code}")
        print(f"Response: {res_sentinel.json()}")

        assert res_sentinel.status_code == 401, f"Expected 401 Unauthorized, got {res_sentinel.status_code}"

        # Inspect all captured server logs
        all_logs_text = "\n".join(log_capture.formatted_logs)
        print(f"Captured Logs ({len(log_capture.formatted_logs)} entries):")
        for log_entry in log_capture.formatted_logs:
            print(f"  -> {log_entry}")

        # Assert sentinel value never appears in any server log output
        assert sentinel_key not in all_logs_text, f"SECURITY VIOLATION: Sentinel '{sentinel_key}' found in logs!"

        # Confirm request ID and request metadata ARE logged
        assert sentinel_req_id in all_logs_text, f"Expected request_id '{sentinel_req_id}' in logs"
        assert "401" in all_logs_text, "Expected status_code 401 in logs"
        assert "/api/v1/links" in all_logs_text, "Expected route in logs"
        assert "latency_ms" in all_logs_text, "Expected latency_ms in logs"
        print("[PASS] TEST C: Confirmed sentinel 'DO_NOT_LOG_ME_123' absent from all logs; metadata present")
        passed_checks += 1

        # =====================================================================
        # TEST D: Request ID Handling (Propagation & Sanitization)
        # =====================================================================
        print("\n--- TEST D: Request ID Validation and Sanitization ---")
        total_checks += 1
        # 1. Valid custom ID
        valid_custom_id = "custom-trace-uuid-abcdef-123456"
        res_custom = client.get("/health", headers={"X-Request-ID": valid_custom_id})
        assert res_custom.headers.get("X-Request-ID") == valid_custom_id
        print(f"[PASS] TEST D1: Valid custom X-Request-ID preserved: {valid_custom_id}")

        # 2. Malformed / malicious custom ID (contains header injection / script tags)
        malicious_id = "<script>alert('xss')</script>\r\nInjected-Header: evil"
        res_malicious = client.get("/health", headers={"X-Request-ID": malicious_id})
        sanitized_id = res_malicious.headers.get("X-Request-ID")
        assert sanitized_id != malicious_id, "Security hole: Malformed X-Request-ID was trusted!"
        assert sanitized_id.startswith("req_"), f"Expected sanitized req_ prefix, got {sanitized_id}"
        print(f"[PASS] TEST D2: Malicious X-Request-ID safely rejected and replaced with: {sanitized_id}")
        passed_checks += 1

        # =====================================================================
        # TEST E: Consistent Error Envelopes Across All HTTP Status Codes
        # =====================================================================
        print("\n--- TEST E: Verification of 401, 404, 410, and 429 Status Codes ---")
        # 1. 401 Unauthorized
        total_checks += 1
        res_401 = client.get("/links")
        assert res_401.status_code == 401
        assert res_401.json()["error"]["code"] == "UNAUTHORIZED"
        assert res_401.headers.get("WWW-Authenticate") == "ApiKey"
        assert res_401.headers.get("X-Request-ID") is not None
        print("[PASS] TEST E1: 401 returns UNAUTHORIZED envelope with WWW-Authenticate and X-Request-ID")
        passed_checks += 1

        # 2. 404 Not Found
        total_checks += 1
        res_404 = client.get("/r/nonexistent-code-xyz", follow_redirects=False)
        assert res_404.status_code == 404
        assert res_404.json()["error"]["code"] == "NOT_FOUND"
        assert res_404.headers.get("X-Request-ID") is not None
        print("[PASS] TEST E2: 404 returns NOT_FOUND envelope with X-Request-ID")
        passed_checks += 1

        # 3. 410 Gone
        total_checks += 1
        db = SessionLocal()
        try:
            exp_code = "m5_exp_code"
            db.query(ClickEvent).filter(ClickEvent.link_id.in_(
                db.query(Link.id).filter(Link.code == exp_code)
            )).delete(synchronize_session=False)
            db.query(Link).filter(Link.code == exp_code).delete(synchronize_session=False)
            db.commit()

            exp_link = Link(
                code=exp_code,
                long_url="https://example.com/expired-target",
                created_by="org_a",
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
            )
            db.add(exp_link)
            db.commit()
        finally:
            db.close()

        res_410 = client.get(f"/r/{exp_code}", follow_redirects=False)
        assert res_410.status_code == 410
        assert res_410.json()["error"]["code"] == "GONE"
        assert res_410.headers.get("X-Request-ID") is not None
        print("[PASS] TEST E3: 410 returns GONE envelope with X-Request-ID")
        passed_checks += 1

        # 4. 429 Rate Limited
        total_checks += 1
        rate_limiter.reset()
        throttled = False
        retry_header = None
        for i in range(35):
            r = client.post(
                "/links",
                headers={"X-API-Key": "API_KEY_A"},
                json={"long_url": f"https://example.com/m5-rate-{i}"}
            )
            if r.status_code == 429:
                throttled = True
                retry_header = r.headers.get("Retry-After")
                assert r.json()["error"]["code"] == "RATE_LIMITED"
                assert r.headers.get("X-Request-ID") is not None
                break

        assert throttled, "Expected 429 after exceeding limit"
        assert retry_header is not None, "Expected Retry-After header on 429"
        print(f"[PASS] TEST E4: 429 returns RATE_LIMITED envelope with Retry-After: {retry_header}")
        passed_checks += 1

        # =====================================================================
        # SUMMARY
        # =====================================================================
        print("\n" + "=" * 75)
        print(f"VERIFICATION RESULTS: {passed_checks}/{total_checks} CHECKS PASSED")
        print("=" * 75)

    finally:
        root_logger.removeHandler(log_capture)


if __name__ == "__main__":
    run_tests()
