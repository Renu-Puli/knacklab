"""
Module 06 BREAK Reproduction Script
Difficulty: Medium (Cache not invalidated on update)

Steps:
1. Create a short link with an initial URL.
2. Trigger GET /r/{code} to warm/populate the Redis cache with the initial URL.
3. Confirm Redis has the cached entry pointing to initial URL.
4. Send PATCH /links/{id} with a new URL -> returns HTTP 200.
5. Query PostgreSQL directly -> confirm PostgreSQL has the NEW URL.
6. Query Redis directly -> show Redis still has the OLD URL.
7. Send GET /r/{code} -> demonstrate it redirects to the STALE OLD URL instead of the new URL.
"""
import sys
import os
import json
import httpx
from datetime import datetime, timezone

# Ensure apps/api is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import SessionLocal
from app.models import Link
import app.cache as cache_module
from app.cache import get_cache_key, init_redis, close_redis

HEADERS_ORG_A = {"X-API-Key": "test-api-key-org-a"}


async def reproduce():
    print("=" * 70)
    print("MODULE 06 BREAK REPRODUCTION: Cache Not Invalidated on Update")
    print("=" * 70)

    await init_redis()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        # Step 1: Create link
        initial_url = "https://example.com/initial-v1-destination"
        create_res = await client.post(
            "/links",
            json={"long_url": initial_url},
            headers=HEADERS_ORG_A,
        )
        assert create_res.status_code == 201, f"Create failed: {create_res.text}"
        link_data = create_res.json()
        link_id = link_data["id"]
        code = link_data["code"]
        print(f"\n[Step 1] Created short link:")
        print(f"  Link ID:     {link_id}")
        print(f"  Short Code:  {code}")
        print(f"  Initial URL: {initial_url}")

        # Step 2: Trigger redirect to warm Redis cache
        r1 = await client.get(f"/r/{code}")
        assert r1.status_code == 307
        assert r1.headers["location"] == initial_url
        print(f"\n[Step 2] Warmed cache via GET /r/{code}:")
        print(f"  Status:   {r1.status_code} Temporary Redirect")
        print(f"  Location: {r1.headers['location']}")

        # Step 3: Inspect Redis cache
        key = get_cache_key(code)
        raw_cached = await cache_module.redis_client.get(key)
        assert raw_cached is not None
        cached_json = json.loads(raw_cached)
        print(f"\n[Step 3] Verified Redis cache entry ({key}):")
        print(f"  Cached Long URL: {cached_json['long_url']}")
        print(f"  Cached Org ID:   {cached_json['org_id']}")
        assert cached_json["long_url"] == initial_url

        # Step 4: Send PATCH /links/{id} with new URL
        new_url = "https://example.com/updated-v2-destination-2026"
        patch_res = await client.patch(
            f"/links/{link_id}",
            json={"long_url": new_url},
            headers=HEADERS_ORG_A,
        )
        assert patch_res.status_code == 200, f"PATCH failed: {patch_res.text}"
        print(f"\n[Step 4] Submitted PATCH /links/{link_id}:")
        print(f"  Status:       {patch_res.status_code} OK")
        print(f"  Payload sent: {new_url}")
        print(f"  Returned URL: {patch_res.json()['long_url']}")

        # Step 5: Check PostgreSQL database directly (Source of Truth)
        db = SessionLocal()
        try:
            db_link = db.query(Link).filter(Link.id == link_id).first()
            assert db_link is not None
            pg_url = db_link.long_url
            print(f"\n[Step 5] Direct PostgreSQL query:")
            print(f"  PostgreSQL long_url: {pg_url}")
            assert pg_url == new_url, "PostgreSQL should have the new URL"
            print("  -> PostgreSQL successfully committed the new URL.")
        finally:
            db.close()

        # Step 6: Check Redis cache key again
        raw_cached_after = await cache_module.redis_client.get(key)
        print(f"\n[Step 6] Inspecting Redis cache entry after PATCH:")
        if raw_cached_after is not None:
            cached_after_json = json.loads(raw_cached_after)
            stale_cached_url = cached_after_json.get("long_url")
            print(f"  Redis key '{key}' still exists!")
            print(f"  Redis cached long_url: {stale_cached_url}")
            if stale_cached_url == initial_url:
                print("  [BUG OBSERVED] Redis still holds the STALE OLD URL!")
        else:
            print("  Redis key was evicted (Bug not present).")

        # Step 7: Request public redirect GET /r/{code}
        r2 = await client.get(f"/r/{code}")
        print(f"\n[Step 7] Requesting public redirect GET /r/{code}:")
        print(f"  HTTP Status Code: {r2.status_code}")
        print(f"  Location Header:  {r2.headers.get('location')}")
        print(f"  Expected (PostgreSQL): {new_url}")
        print(f"  Actual (Served):       {r2.headers.get('location')}")

        if r2.headers.get("location") == initial_url:
            print("\n" + "!" * 70)
            print("SYMPTOM CONFIRMED: STALE REDIRECT SERVED TO CLIENT!")
            print(f"PostgreSQL holds: {new_url}")
            print(f"Client received:  {r2.headers.get('location')} (STALE!)")
            print("!" * 70)
            return True
        else:
            print("\nSymptom was NOT reproduced.")
            return False

    await close_redis()


if __name__ == "__main__":
    import asyncio
    success = asyncio.run(reproduce())
    sys.exit(0 if success else 1)
