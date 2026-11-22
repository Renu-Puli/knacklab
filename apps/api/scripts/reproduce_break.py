import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Link
from app.logging_config import RedactingFilter, StructuredJsonFormatter

client = TestClient(app, raise_server_exceptions=False)


class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.formatted_logs = []
        self.addFilter(RedactingFilter())
        self.setFormatter(StructuredJsonFormatter())

    def emit(self, record):
        self.formatted_logs.append(self.format(record))


def verify_fix():
    print("=" * 70)
    print("=== MODULE 05 STEP 6: FIX VERIFICATION SUITE ===")
    print("Verification of Database Transaction Integrity and Safe 500 Propagation")
    print("=" * 70)

    log_capture = LogCaptureHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(log_capture)

    try:
        # -------------------------------------------------------------
        # CHECK 1: Normal Link Creation & Database Persistence
        # -------------------------------------------------------------
        print("\n[CHECK 1] Testing normal link creation and database persistence...")
        res_normal = client.post(
            "/api/v1/links",
            headers={"X-API-Key": "API_KEY_A"},
            json={"long_url": "https://example.com/fix-verified-destination"}
        )
        print(f"Status: {res_normal.status_code}")
        data_normal = res_normal.json()
        print(f"Response: {data_normal}")

        assert res_normal.status_code == 201, f"Expected 201, got {res_normal.status_code}"
        assert data_normal["id"] != 999999, "Returned fabricated fake ID 999999!"
        assert data_normal["id"] > 0, "Expected valid database ID"
        code = data_normal["code"]

        # Confirm record persisted in PostgreSQL
        db = SessionLocal()
        try:
            record = db.query(Link).filter(Link.code == code).first()
            assert record is not None, f"Record with code '{code}' not found in PostgreSQL!"
            assert record.long_url == "https://example.com/fix-verified-destination"
            print(f"[PASS] CHECK 1: Link {record.id} (code: {code}) verified in PostgreSQL")
        finally:
            db.close()

        # Confirm public redirect works
        res_redir = client.get(f"/r/{code}", follow_redirects=False)
        assert res_redir.status_code == 307
        assert res_redir.headers.get("location") == "https://example.com/fix-verified-destination"
        print("[PASS] CHECK 1B: Public redirect GET /r/{code} returned 307 with location")

        # -------------------------------------------------------------
        # CHECK 2: Database Failure Propagation & Global 500 Handling
        # -------------------------------------------------------------
        print("\n[CHECK 2] Testing simulated database failure handling (no swallowed exceptions)...")
        test_req_id = "req_fix_verify_db_fail_500"
        simulated_err = "Database connection timed out during commit"

        log_capture.formatted_logs.clear()

        with patch("sqlalchemy.orm.Session.commit", side_effect=Exception(simulated_err)):
            res_fail = client.post(
                "/api/v1/links",
                headers={
                    "X-API-Key": "API_KEY_A",
                    "X-Request-ID": test_req_id,
                },
                json={"long_url": "https://example.com/should-fail-gracefully"}
            )

        print(f"Status: {res_fail.status_code}")
        data_fail = res_fail.json()
        print(f"Response Body: {json.dumps(data_fail, indent=2)}")
        print(f"X-Request-ID Header: {res_fail.headers.get('X-Request-ID')}")

        # Assert no fake success was returned
        assert res_fail.status_code == 500, f"Expected HTTP 500, got {res_fail.status_code}"
        assert res_fail.status_code != 201, "Defect detected: Returned HTTP 201 on database failure!"
        assert "error" in data_fail, "Response must contain error envelope"

        err = data_fail["error"]
        assert err["code"] == "INTERNAL_ERROR", f"Expected code 'INTERNAL_ERROR', got {err.get('code')}"
        assert err["message"] == "Internal server error", "Expected generic 'Internal server error'"
        assert err["request_id"] == test_req_id, f"Expected request_id {test_req_id}"
        assert res_fail.headers.get("X-Request-ID") == test_req_id

        # Assert zero stack traces or internal exception details leaked to client
        raw_resp = json.dumps(data_fail)
        assert simulated_err not in raw_resp, "Security leak: Raw exception text in client response!"
        assert "Traceback" not in raw_resp, "Security leak: Python traceback in client response!"

        # Assert server logs contain matching request_id
        matched_logs = [l for l in log_capture.formatted_logs if test_req_id in l]
        assert len(matched_logs) > 0, "Server logs do not contain the error request_id"
        print("[PASS] CHECK 2: Database failure safely propagated to global 500 handler; logs correlated")

        print("\n" + "=" * 70)
        print("[PASS] Application transaction handling and error propagation verified successfully.")
        print("The injected swallowed-exception error is completely resolved.")
        print("=" * 70)
        return True

    finally:
        root_logger.removeHandler(log_capture)


if __name__ == "__main__":
    success = verify_fix()
    if not success:
        sys.exit(1)
