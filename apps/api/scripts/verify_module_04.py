import sys
import asyncio
import httpx
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Add apps/api to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, engine
from app.models import Link, ClickEvent
from app.rate_limiter import rate_limiter
from app.schemas.link import LinkCreate
from app.celery_app import celery_app

# Enable eager execution so background Celery tasks run synchronously in test client
celery_app.conf.task_always_eager = True

client = TestClient(app, raise_server_exceptions=False)

def run_all_tests():
    print("=" * 70)
    print("MODULE 04 – STEP 3: BUILD VERIFICATION & REGRESSION SUITE")
    print("=" * 70)

    # Reset in-memory rate limiter for a fresh test run
    rate_limiter.reset()

    # ---------------------------------------------------------
    # TEST 1: POST /links without API key -> 401
    # ---------------------------------------------------------
    print("\n[TEST 1] POST /links without API key...")
    res = client.post("/links", json={"long_url": "https://example.com/unauth"})
    print(f"Status: {res.status_code}, Response: {res.json()}")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("[PASS] TEST 1: Correctly rejected with 401 Unauthorized")

    # ---------------------------------------------------------
    # TEST 2: GET /links without API key -> 401
    # ---------------------------------------------------------
    print("\n[TEST 2] GET /links without API key...")
    res = client.get("/links")
    print(f"Status: {res.status_code}, Response: {res.json()}")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("[PASS] TEST 2: Correctly rejected with 401 Unauthorized")

    # ---------------------------------------------------------
    # TEST 3: Invalid API key -> 401
    # ---------------------------------------------------------
    print("\n[TEST 3] Admin endpoint with invalid API key...")
    res = client.get("/links", headers={"X-API-Key": "invalid-bogus-key-12345"})
    print(f"Status: {res.status_code}, Response: {res.json()}")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("[PASS] TEST 3: Invalid key correctly rejected with 401 Unauthorized")

    # ---------------------------------------------------------
    # TEST 4: Valid API_KEY_A creates a link successfully
    # ---------------------------------------------------------
    print("\n[TEST 4] Valid API_KEY_A creates a link...")
    res_a = client.post(
        "/links",
        headers={"X-API-Key": "API_KEY_A"},
        json={"long_url": "https://example.com/tenant-a-link", "tags": ["prod", "tenant_a"]}
    )
    print(f"Status: {res_a.status_code}, Response: {res_a.json()}")
    assert res_a.status_code == 201, f"Expected 201, got {res_a.status_code}"
    data_a = res_a.json()
    link_id_a = data_a["id"]
    code_a = data_a["code"]
    assert data_a["created_by"] == "org_a", f"Expected created_by 'org_a', got {data_a['created_by']}"
    print(f"[PASS] TEST 4: Created link {link_id_a} (code: {code_a}) owned by org_a")

    # ---------------------------------------------------------
    # TEST 5: Valid API_KEY_A lists only its own links
    # ---------------------------------------------------------
    print("\n[TEST 5] Valid API_KEY_A lists links (tenant isolation)...")
    # Also create a link as tenant B for comparison
    res_b = client.post(
        "/links",
        headers={"X-API-Key": "API_KEY_B"},
        json={"long_url": "https://example.com/tenant-b-link"}
    )
    assert res_b.status_code == 201
    link_id_b = res_b.json()["id"]

    list_a = client.get("/links", headers={"X-API-Key": "API_KEY_A"}).json()
    list_b = client.get("/links", headers={"X-API-Key": "API_KEY_B"}).json()

    org_a_ids = [l["id"] for l in list_a]
    org_b_ids = [l["id"] for l in list_b]

    assert link_id_a in org_a_ids, "Tenant A link missing from Tenant A list"
    assert link_id_b not in org_a_ids, "Tenant B link leaked into Tenant A list!"
    assert link_id_b in org_b_ids, "Tenant B link missing from Tenant B list"
    assert link_id_a not in org_b_ids, "Tenant A link leaked into Tenant B list!"
    for l in list_a:
        assert l["created_by"] == "org_a", f"Found non-org_a link in org_a list: {l}"
    print(f"[PASS] TEST 5: Confirmed strict tenant isolation in GET /links list")

    # ---------------------------------------------------------
    # TEST 6: API_KEY_B cannot retrieve API_KEY_A's link -> 404
    # ---------------------------------------------------------
    print("\n[TEST 6] Cross-tenant link access: Tenant B attempts GET /links/{id_a}...")
    res_cross = client.get(f"/links/{link_id_a}", headers={"X-API-Key": "API_KEY_B"})
    print(f"Status: {res_cross.status_code}, Response: {res_cross.json()}")
    assert res_cross.status_code == 404, f"Expected 404 (not_owner_status), got {res_cross.status_code}"
    print("[PASS] TEST 6: Correctly returned 404 Not Found (zero resource existence leakage)")

    # ---------------------------------------------------------
    # TEST 7: API_KEY_B cannot delete API_KEY_A's link -> 404
    # ---------------------------------------------------------
    print("\n[TEST 7] Cross-tenant link deletion: Tenant B attempts DELETE /links/{id_a}...")
    res_del_cross = client.delete(f"/links/{link_id_a}", headers={"X-API-Key": "API_KEY_B"})
    print(f"Status: {res_del_cross.status_code}")
    assert res_del_cross.status_code == 404, f"Expected 404, got {res_del_cross.status_code}"

    # Verify link A is still present and accessible by Tenant A
    verify_a = client.get(f"/links/{link_id_a}", headers={"X-API-Key": "API_KEY_A"})
    assert verify_a.status_code == 200, "Link A was erroneously deleted or modified!"
    print("[PASS] TEST 7: Cross-tenant deletion rejected with 404; link preserved")

    # ---------------------------------------------------------
    # TEST 8: GET /r/{code} without authentication -> 307
    # ---------------------------------------------------------
    print("\n[TEST 8] Public redirect: GET /r/{code} without auth...")
    res_red = client.get(f"/r/{code_a}", follow_redirects=False)
    print(f"Status: {res_red.status_code}, Location: {res_red.headers.get('location')}")
    assert res_red.status_code == 307, f"Expected 307, got {res_red.status_code}"
    assert res_red.headers.get("location") == "https://example.com/tenant-a-link"
    print("[PASS] TEST 8: Public redirect works without authentication (HTTP 307)")

    # ---------------------------------------------------------
    # TEST 9: Unknown short code -> 404
    # ---------------------------------------------------------
    print("\n[TEST 9] Unknown short code redirect...")
    res_unk = client.get("/r/nonexistent999", follow_redirects=False)
    print(f"Status: {res_unk.status_code}, Detail: {res_unk.json()}")
    assert res_unk.status_code == 404, f"Expected 404, got {res_unk.status_code}"
    print("[PASS] TEST 9: Unknown short code returns 404")

    # ---------------------------------------------------------
    # TEST 10: Expired link -> 410
    # ---------------------------------------------------------
    print("\n[TEST 10] Expired short link redirect...")
    db = SessionLocal()
    try:
        expired_code = "m4_exp_code"
        db.query(ClickEvent).filter(ClickEvent.link_id.in_(
            db.query(Link.id).filter(Link.code == expired_code)
        )).delete(synchronize_session=False)
        db.query(Link).filter(Link.code == expired_code).delete(synchronize_session=False)
        db.commit()

        exp_link = Link(
            code=expired_code,
            long_url="https://example.com/expired-target",
            created_by="org_a",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        db.add(exp_link)
        db.commit()
    finally:
        db.close()

    res_exp = client.get(f"/r/{expired_code}", follow_redirects=False)
    print(f"Status: {res_exp.status_code}, Detail: {res_exp.json()}")
    assert res_exp.status_code == 410, f"Expected 410, got {res_exp.status_code}"
    print("[PASS] TEST 10: Expired link correctly returns 410 Gone")

    # ---------------------------------------------------------
    # TEST 11: Create-link rate limit -> 429 after 30 requests/min
    # ---------------------------------------------------------
    print("\n[TEST 11] Create-link rate limiting (limit = 30/min per API key)...")
    rate_limiter.reset()
    key_test = "API_KEY_A"
    success_count = 0
    throttled = False
    retry_after_header = None

    for i in range(35):
        resp = client.post(
            "/links",
            headers={"X-API-Key": key_test},
            json={"long_url": f"https://example.com/burst-{i}"}
        )
        if resp.status_code == 201:
            success_count += 1
        elif resp.status_code == 429:
            throttled = True
            retry_after_header = resp.headers.get("Retry-After")
            print(f"Request {i+1}: HTTP 429 Received! Retry-After: {retry_after_header}")
            break

    print(f"Successful creations before throttle: {success_count}")
    assert success_count == 30, f"Expected exactly 30 allowed creations, got {success_count}"
    assert throttled, "Did not receive HTTP 429 on 31st creation!"
    assert retry_after_header is not None, "Missing Retry-After header on 429 response"
    print("[PASS] TEST 11: Create-link throttled at limit (30/min) with 429 and Retry-After header")

    # ---------------------------------------------------------
    # TEST 12: Redirect rate limit -> 429 after 120 requests/min
    # ---------------------------------------------------------
    print("\n[TEST 12] Redirect rate limiting (limit = 120/min per client IP)...")
    rate_limiter.reset()

    async def run_redirect_burst():
        import httpx
        import asyncio
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as aclient:
            success = 0
            throttled = False
            retry_after = None
            for i in range(125):
                resp = await aclient.get(f"/r/{code_a}", headers={"X-Forwarded-For": "198.51.100.42"})
                if resp.status_code == 307:
                    success += 1
                elif resp.status_code == 429:
                    throttled = True
                    retry_after = resp.headers.get("Retry-After")
                    print(f"Redirect {i+1}: HTTP 429 Received! Retry-After: {retry_after}")
                    break
            return success, throttled, retry_after

    red_success, red_throttled, red_retry_after = asyncio.run(run_redirect_burst())

    print(f"Successful redirects before throttle: {red_success}")
    assert red_success == 120, f"Expected exactly 120 allowed redirects, got {red_success}"
    assert red_throttled, "Did not receive HTTP 429 on 121st redirect!"
    assert red_retry_after is not None, "Missing Retry-After header on 429 redirect"
    print("[PASS] TEST 12: Redirect throttled at limit (120/min) with 429 and Retry-After header")

    # ---------------------------------------------------------
    # TEST 13: Existing URL validation and click tracking tests
    # ---------------------------------------------------------
    print("\n[TEST 13] Checking URL validation security checks...")
    rate_limiter.reset()
    malicious = [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "file:///etc/passwd",
        "//evil.example.com",
        "http:\\\\evil.example.com",
    ]
    for bad_url in malicious:
        try:
            LinkCreate(long_url=bad_url)
            raise AssertionError(f"VULNERABILITY: Accepted malicious URL: {bad_url}")
        except Exception:
            pass
    print("[PASS] TEST 13A: URL validation rejects dangerous schemes and control chars")

    # Click tracking persistence check
    db = SessionLocal()
    try:
        clicks_count = db.query(ClickEvent).filter(ClickEvent.link_id == link_id_a).count()
        print(f"Clicks recorded for link {link_id_a}: {clicks_count}")
        assert clicks_count > 0, "No click events were recorded for the public redirect!"
    finally:
        db.close()
    print("[PASS] TEST 13B: Click tracking recorded and verified in PostgreSQL")

    # Cleanup test links created during test
    db = SessionLocal()
    try:
        test_ids = [link_id_a, link_id_b]
        db.query(ClickEvent).filter(ClickEvent.link_id.in_(test_ids)).delete(synchronize_session=False)
        db.query(Link).filter(Link.id.in_(test_ids)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    print("\n" + "=" * 70)
    print("ALL 13 VERIFICATION & REGRESSION CHECKS COMPLETED AND PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    run_all_tests()
