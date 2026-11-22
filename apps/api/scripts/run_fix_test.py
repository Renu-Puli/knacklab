import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Add apps/api to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Link, ClickEvent
from app.routers.redirect import redirect_short_code, router
from starlette.requests import Request
from fastapi import HTTPException

def run_regression_tests():
    print("=== MODULE 03 STEP 6: FIX VERIFICATION & REGRESSION SUITE ===")
    
    # 1. Verify route method registration
    route = next(r for r in router.routes if r.path == "/r/{code}")
    print(f"Route Path: {route.path}")
    print(f"Registered HTTP Methods: {route.methods}")
    assert "GET" in route.methods, "GET method is not registered on /r/{code}!"
    print("[PASS] Confirmed 'GET' is registered on /r/{code}")

    # 2. Database & Request Verification
    db = SessionLocal()
    try:
        active_code = "fix_ok"
        expired_code = "fix_exp"
        
        # Clean up existing test keys if any
        db.query(ClickEvent).filter(ClickEvent.link_id.in_(
            db.query(Link.id).filter(Link.code.in_([active_code, expired_code]))
        )).delete(synchronize_session=False)
        db.query(Link).filter(Link.code.in_([active_code, expired_code])).delete(synchronize_session=False)
        db.commit()

        link_active = Link(
            code=active_code,
            long_url="https://example.com/destination-verified",
            created_by="fix_verification",
        )
        link_expired = Link(
            code=expired_code,
            long_url="https://example.com/expired-target",
            created_by="fix_verification",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        db.add_all([link_active, link_expired])
        db.commit()
        db.refresh(link_active)
        db.refresh(link_expired)

        def make_req(code: str):
            return Request({
                "type": "http",
                "method": "GET",
                "path": f"/r/{code}",
                "headers": [
                    (b"host", b"localhost:8000"),
                    (b"user-agent", b"FixVerificationRunner/1.0"),
                    (b"referer", b"https://referrer.example.com"),
                ],
                "scheme": "http",
                "server": ("localhost", 8000),
                "client": ("127.0.0.1", 54321),
            })

        # Test A: GET /r/{code} returns HTTP 307 with correct Location
        resp = redirect_short_code(code=active_code, request=make_req(active_code), db=db)
        print(f"[TEST A - REDIRECT SUCCESS] Status: {resp.status_code}, Location: {resp.headers.get('location')}")
        assert resp.status_code == 307
        assert resp.headers.get("location") == "https://example.com/destination-verified"

        # Test B: Unknown short code returns HTTP 404
        try:
            redirect_short_code(code="unknown_xyz_404", request=make_req("unknown_xyz_404"), db=db)
            raise AssertionError("Expected 404 for unknown code, but it passed!")
        except HTTPException as e:
            print(f"[TEST B - UNKNOWN CODE] Status: {e.status_code}, Detail: {e.detail}")
            assert e.status_code == 404

        # Test C: Expired link returns HTTP 410 Gone
        try:
            redirect_short_code(code=expired_code, request=make_req(expired_code), db=db)
            raise AssertionError("Expected 410 for expired code, but it passed!")
        except HTTPException as e:
            print(f"[TEST C - EXPIRED LINK] Status: {e.status_code}, Detail: {e.detail}")
            assert e.status_code == 410

        # Test D: Click tracking failure does not fail the redirect
        with patch.object(db, "commit", side_effect=Exception("Simulated background click tracking DB failure")):
            resp_resilient = redirect_short_code(code=active_code, request=make_req(active_code), db=db)
            print(f"[TEST D - ANALYTICS RESILIENCE] Status: {resp_resilient.status_code}, Location: {resp_resilient.headers.get('location')}")
            assert resp_resilient.status_code == 307
            assert resp_resilient.headers.get("location") == "https://example.com/destination-verified"

        print("\n=== ALL REGRESSION AND FIX TESTS COMPLETED AND PASSED ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_regression_tests()

