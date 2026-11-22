import os
import sys
import json
import io
import logging
import uuid
from starlette.testclient import TestClient

# Add apps/api to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from app.logging_config import (
    configure_logging,
    sanitize_log_text,
    redact_text,
    redact_dict,
    RedactingFilter,
    StructuredJsonFormatter,
    log_request_event,
    logger,
)
from app.main import app

def test_sanitize_log_text_unit():
    print("=== 1. sanitize_log_text Unit Tests ===")

    # Test 1.1: Neutralizes newlines and carriage returns
    raw_crlf = "line1\r\nline2\nline3\rline4"
    sanitized_crlf = sanitize_log_text(raw_crlf)
    assert "\n" not in sanitized_crlf
    assert "\r" not in sanitized_crlf
    assert sanitized_crlf == "line1\\r\\nline2\\nline3\\rline4"
    print("  [PASS] 1.1: CR and LF characters safely converted to escaped representations.")

    # Test 1.2: Strips non-printable control characters
    raw_control = "hello\x00\x07world\x1b[31m!"
    sanitized_control = sanitize_log_text(raw_control)
    assert "\x00" not in sanitized_control
    assert "\x07" not in sanitized_control
    assert "\x1b" not in sanitized_control
    print("  [PASS] 1.2: Dangerous non-printable control characters stripped.")

    # Test 1.3: Preserves legitimate URLs
    clean_url = "https://example.com:8080/path/to/resource?search=query%20item&sort=desc#section"
    assert sanitize_log_text(clean_url) == clean_url
    print("  [PASS] 1.3: Legitimate complex URL preserved completely intact.")


def test_redact_text_combined():
    print("\n=== 2. redact_text Combined Sanitization and Redaction ===")

    # Test 2.1: Redacts credentials while neutralizing newlines
    mixed_payload = (
        "User action\n"
        "Authorization: Bearer my-secret-jwt-token-12345\n"
        "API_KEY: test-api-key-org-a\n"
        "Sentinel: DO_NOT_LOG_ME_123"
    )
    redacted = redact_text(mixed_payload)
    assert "\n" not in redacted
    assert "my-secret-jwt-token-12345" not in redacted
    assert "test-api-key-org-a" not in redacted
    assert "DO_NOT_LOG_ME_123" not in redacted
    assert "[REDACTED]" in redacted
    print("  [PASS] 2.1: Secrets redacted and newlines neutralized simultaneously.")


def test_redacting_filter_and_formatter():
    print("\n=== 3. RedactingFilter and StructuredJsonFormatter Anti-Forgery Tests ===")

    # Bob's exact forged payload from STEP 5 forensic investigation
    forged_input = (
        'https://normal-url.com\n'
        '{"ts":"2026-11-21T18:04:02.105Z","level":"info","req_id":"r-102",'
        '"msg":"admin login successful","user":"admin","ip":"10.0.0.1"}'
    )

    buf = io.StringIO()
    test_logger = logging.getLogger("anti_forgery_test")
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.INFO)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(StructuredJsonFormatter())
    test_logger.addHandler(handler)

    # Log with request_id = r-101
    extra = {"request_id": "r-101"}
    test_logger.info(f"link created: {forged_input}", extra=extra)

    handler.flush()
    raw_output = buf.getvalue().strip()

    # Verify exactly 1 line is produced (no multiline log splitting)
    lines = raw_output.splitlines()
    assert len(lines) == 1, f"Expected exactly 1 line, got {len(lines)}"
    print(f"  [PASS] 3.1: Log output is strictly a single line (line count: {len(lines)}).")

    # Verify raw output has no unescaped newline
    assert "\n" not in raw_output
    assert "\r" not in raw_output
    print("  [PASS] 3.2: Output stream contains 0 raw newline or carriage return characters.")

    # Parse JSON
    parsed = json.loads(raw_output)
    assert parsed["request_id"] == "r-101", f"Expected r-101, got {parsed['request_id']}"
    assert parsed["level"] == "INFO"
    assert "admin login successful" in parsed["message"]
    print("  [PASS] 3.3: Injected log line is quarantined as literal string inside message field.")
    print("  [PASS] 3.4: True request ID (r-101) and true level (INFO) cannot be forged.")

    # Test argument interpolation anti-forgery
    buf.seek(0)
    buf.truncate(0)
    test_logger.info("Created link %s for tenant", forged_input, extra={"request_id": "r-103"})
    handler.flush()
    raw_arg_output = buf.getvalue().strip()
    arg_lines = raw_arg_output.splitlines()
    assert len(arg_lines) == 1
    parsed_arg = json.loads(raw_arg_output)
    assert parsed_arg["request_id"] == "r-103"
    print("  [PASS] 3.5: Argument-interpolated logging safely escapes injection payload.")


def test_http_api_injection_rejection():
    print("\n=== 4. HTTP API Input Validation and Security Tests ===")
    client = TestClient(app)
    headers = {"X-API-Key": "test-api-key-org-a"}

    # 4.1: Reject URL with newline and forged log payload
    malicious_url_body = {
        "long_url": 'https://normal-url.com\n{"ts":"2026-11-21T18:04:02.105Z","level":"info","req_id":"r-102","msg":"admin login successful"}'
    }
    resp = client.post("/links", json=malicious_url_body, headers=headers)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"
    err_body = resp.json()
    assert err_body["error"]["code"] == "VALIDATION_ERROR"
    assert "prohibited control characters" in err_body["error"]["message"].lower()
    print("  [PASS] 4.1: Malicious URL containing newline rejected with 422 VALIDATION_ERROR.")

    # 4.2: Reject tag with newline
    malicious_tag_body = {
        "long_url": "https://example.com/safe-url",
        "tags": ["safe", "admin\nfake-log-line"]
    }
    resp_tag = client.post("/links", json=malicious_tag_body, headers=headers)
    assert resp_tag.status_code == 422, f"Expected 422, got {resp_tag.status_code}"
    err_tag_body = resp_tag.json()
    assert err_tag_body["error"]["code"] == "VALIDATION_ERROR"
    assert "prohibited control characters" in err_tag_body["error"]["message"].lower()
    print("  [PASS] 4.2: Malicious tag containing newline rejected with 422 VALIDATION_ERROR.")

    # 4.3: Legitimate URL creation succeeds
    legit_body = {
        "long_url": f"https://example.com/legitimate-path-{uuid.uuid4().hex[:6]}",
        "tags": ["marketing", "prod"]
    }
    resp_legit = client.post("/links", json=legit_body, headers=headers)
    assert resp_legit.status_code == 201, f"Expected 201, got {resp_legit.status_code}"
    created_link = resp_legit.json()
    assert created_link["long_url"] == legit_body["long_url"]
    print("  [PASS] 4.3: Legitimate URL created successfully with 201 CREATED.")

    # 4.4: Request correlation header present and clean
    assert "X-Request-ID" in resp_legit.headers
    req_id = resp_legit.headers["X-Request-ID"]
    assert "\n" not in req_id
    assert "\r" not in req_id
    print(f"  [PASS] 4.4: Response contains clean X-Request-ID header: {req_id}")


if __name__ == "__main__":
    print("Starting Bug #5 (Log Injection / CWE-117) Verification Suite...\n")
    test_sanitize_log_text_unit()
    test_redact_text_combined()
    test_redacting_filter_and_formatter()
    test_http_api_injection_rejection()
    print("\n========================================================")
    print("ALL BUG #5 (LOG INJECTION / CWE-117) TESTS PASSED!")
    print("========================================================")
