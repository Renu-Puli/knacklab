"""
Module 06 FIX Verification Script
Tests the repair of the Medium difficulty defect (cache invalidation on link update).

Verification Sequence:
1. Create a short link with an initial URL.
2. Warm the Redis cache via GET /r/{code} and verify Redis has the initial URL cached.
3. Send PATCH /links/{id} with a new destination URL.
4. Confirm the PATCH operation succeeds with HTTP 200.
5. Confirm the Redis cache key has been invalidated (key no longer exists in Redis).
6. Request GET /r/{code}.
7. Confirm the redirect returns HTTP 307 pointing to the NEW destination URL.
8. Confirm Redis has now been populated with the NEW destination URL.
"""
import sys
import os
import json
import httpx
import asyncio

# Ensure apps/api is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import SessionLocal
from app.models import Link
import app.cache as cache_module
from app.cache import get_cache_key, init_redis, close_redis

HEADERS_ORG_A = {"X-API-Key": "test-api-key-org-a"}


async def verify_fix():
    print("=" * 70)
    print("MODULE 06 FIX VERIFICATION: Proving Cache Invalidation on Update")
    print("=" * 70)

    await init_redis()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        # Step 1: Create short link
        initial_url = "https://example.com/original-destination-v1"
        create_res = await client.post(
            "/links",
            json={"long_url": initial_url},
            headers=HEADERS_ORG_A,
        )
        assert create_res.status_code == 201, f"Create link failed: {create_res.text}"
        link_data = create_res.json()
        link_id = link_data["id"]
        code = link_data["code"]
        print(f"\n[Step 1] Created short link:")
        print(f"  Link ID:     {link_id}")
        print(f"  Short Code:  {code}")
        print(f"  Initial URL: {initial_url}")

        # Step 2: Warm cache via redirect
        r1 = await client.get(f"/r/{code}")
        assert r1.status_code == 307, f"Expected 307, got {r1.status_code}"
        assert r1.headers["location"] == initial_url
        print(f"\n[Step 2] Warmed cache via GET /r/{code}:")
        print(f"  Status:   {r1.status_code} Temporary Redirect")
        print(f"  Location: {r1.headers['location']}")

        # Verify key exists in Redis with initial URL
        key = get_cache_key(code)
        cached_before = await cache_module.redis_client.get(key)
        assert cached_before is not None, "Redis cache should be populated after redirect"
        cached_json_before = json.loads(cached_before)
        print(f"  Redis key '{key}' payload before update:")
        print(f"    long_url: {cached_json_before['long_url']}")
        print(f"    org_id:   {cached_json_before['org_id']}")
        assert cached_json_before["long_url"] == initial_url

        # Step 3 & 4: Send PATCH /links/{id} with new URL
        new_url = "https://example.com/repaired-destination-v2-verified"
        patch_res = await client.patch(
            f"/links/{link_id}",
            json={"long_url": new_url},
            headers=HEADERS_ORG_A,
        )
        assert patch_res.status_code == 200, f"PATCH failed: {patch_res.text}"
        print(f"\n[Step 3 & 4] Sent PATCH /links/{link_id}:")
        print(f"  Status:       {patch_res.status_code} OK")
        print(f"  Returned URL: {patch_res.json()['long_url']}")
        assert patch_res.json()["long_url"] == new_url

        # Confirm PostgreSQL holds new URL
        db = SessionLocal()
        try:
            db_link = db.query(Link).filter(Link.id == link_id).first()
            assert db_link is not None
            assert db_link.long_url == new_url
            print(f"  PostgreSQL verified: {db_link.long_url}")
        finally:
            db.close()

        # Step 5: Verify Redis cache key has been invalidated
        cached_after_patch = await cache_module.redis_client.get(key)
        print(f"\n[Step 5] Checking Redis cache key after PATCH:")
        print(f"  Key '{key}' exists in Redis: {cached_after_patch is not None}")
        assert cached_after_patch is None, "CRITICAL: Key should have been evicted from Redis!"
        print("  -> CONFIRMED: Cache entry was successfully evicted upon PATCH commit.")

        # Step 6 & 7: Request public redirect GET /r/{code}
        r2 = await client.get(f"/r/{code}")
        print(f"\n[Step 6 & 7] Requesting public redirect GET /r/{code} after repair:")
        print(f"  HTTP Status Code: {r2.status_code}")
        print(f"  Location Header:  {r2.headers.get('location')}")
        print(f"  Expected URL:     {new_url}")
        assert r2.status_code == 307
        assert r2.headers.get("location") == new_url, f"Expected {new_url}, got {r2.headers.get('location')}"
        print("  -> CONFIRMED: Redirect points to the NEW updated destination!")

        # Step 8: Verify Redis repopulated with new URL
        cached_final = await cache_module.redis_client.get(key)
        assert cached_final is not None, "Redis should be repopulated after redirect miss"
        cached_json_final = json.loads(cached_final)
        print(f"\n[Step 8] Checking Redis cache key after subsequent redirect:")
        print(f"  Key '{key}' repopulated with:")
        print(f"    long_url: {cached_json_final['long_url']}")
        assert cached_json_final["long_url"] == new_url
        print("  -> CONFIRMED: Redis repopulated with updated destination URL.")

    await close_redis()
    print("\n" + "=" * 70)
    print("MODULE 06 FIX VERIFICATION PASSED: All 8 checks succeeded!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = asyncio.run(verify_fix())
    sys.exit(0 if success else 1)
