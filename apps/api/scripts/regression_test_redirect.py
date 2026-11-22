import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Add apps/api to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Link, ClickEvent
from app.routers.redirect import redirect_short_code
from starlette.requests import Request
from fastapi import HTTPException

def run_regression_tests():
    print("=== RUNNING REGRESSION TESTS FOR /r/{code} ===")
    db = SessionLocal()
    try:
        # 1. Setup test links
        active_code = "regress_ok"
        expired_code = "regress_exp"
        
        # Ensure fresh state for regression keys
        db.query(ClickEvent).filter(ClickEvent.link_id.in_(
            db.query(Link.id).filter(Link.code.in_([active_code, expired_code]))
        )).delete(synchronize_session=False)
        db.query(Link).filter(Link.code.in_([active_code, expired_code])).delete(synchronize_session=False)
        db.commit()

        link_active = Link(
            code=active_code,
            long_url="https://example.com/regression-success",
            created_by="regression_test",
        )
        link_expired = Link(
            code=expired_code,
            long_url="https://example.com/expired-target",
            created_by="regression_test",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add_all([link_active, link_expired])
        db.commit()
        db.refresh(link_active)
        db.refresh(link_expired)

        # Standard GET Request
        def make_req(code: str):
            return Request({
                "type": "http",
                "method": "GET",
                "path": f"/r/{code}",
                "headers": [
                    (b"host", b"testserver"),
                    (b"user-agent", b"RegressionRunner/1.0"),
                ],
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("127.0.0.1", 54321),
            })

        # Test A: GET /r/{code} returns HTTP 307 with correct Location
        resp = redirect_short_code(code=active_code, request=make_req(active_code), db=db)
        print(f"[TEST A - VALID REDIRECT] Status: {resp.status_code}, Location: {resp.headers.get('location')}")
        assert resp.status_code == 307
        assert resp.headers.get("location") == "https://example.com/regression-success"

        # Test B: Unknown short codes return HTTP 404
        try:
            redirect_short_code(code="non_existent_code_999", request=make_req("non_existent_code_999"), db=db)
            raise AssertionError("Expected 404 for unknown code, but it passed!")
        except HTTPException as e:
            print(f"[TEST B - UNKNOWN CODE] Caught expected HTTPException: {e.status_code} ({e.detail})")
            assert e.status_code == 404

        # Test C: Expired links do not redirect (return HTTP 410 Gone)
        try:
            redirect_short_code(code=expired_code, request=make_req(expired_code), db=db)
            raise AssertionError("Expected 410 for expired code, but it passed!")
        except HTTPException as e:
            print(f"[TEST C - EXPIRED LINK] Caught expected HTTPException: {e.status_code} ({e.detail})")
            assert e.status_code == 410

        # Test D: Click tracking failure does not fail redirect
        with patch.object(db, "commit", side_effect=Exception("Simulated analytics database error")):
            resp_resilient = redirect_short_code(code=active_code, request=make_req(active_code), db=db)
            print(f"[TEST D - ANALYTICS FAILURE RESILIENCE] Status: {resp_resilient.status_code}, Location: {resp_resilient.headers.get('location')}")
            assert resp_resilient.status_code == 307
            assert resp_resilient.headers.get("location") == "https://example.com/regression-success"

        print("=== ALL REGRESSION TESTS PASSED SUCCESSFULLY ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_regression_tests()

