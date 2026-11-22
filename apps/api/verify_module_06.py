"""
Module 06 Verification Suite: Caching With Redis
Tests:
1. Cache-aside redirect flow (Miss -> PostgreSQL lookup -> Cache population -> Hit)
2. Cache invalidation on link update (PATCH /links/{id})
3. Cache invalidation on link deletion (DELETE /links/{id})
4. Tenant isolation and scoping in cache
5. Graceful degradation when Redis is unavailable (PostgreSQL fallback)
6. Link expiration in cache
"""
import sys
import os
import asyncio
from datetime import datetime, timedelta, timezone

# Ensure apps/api is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

import httpx
from app.main import app
from app.cache import (
    init_redis,
    close_redis,
    get_redirect_target,
    set_redirect_target,
    invalidate_redirect_target,
    cache_metrics,
    reset_cache_metrics,
    get_cache_key,
)
import app.cache as cache_module

API_KEY_A = "test-api-key-org-a"
API_KEY_B = "test-api-key-org-b"

HEADERS_ORG_A = {"X-API-Key": API_KEY_A}
HEADERS_ORG_B = {"X-API-Key": API_KEY_B}


async def run_tests():
    print("=" * 60)
    print("Running Module 06 Verification Suite: Caching With Redis")
    print("=" * 60)

    # Reset metrics and initialize redis
    reset_cache_metrics()
    await init_redis()

    passed = 0
    total = 0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        # ---------------------------------------------------------
        # Test 1: Cache Miss followed by Cache Hit (Cache-Aside)
        # ---------------------------------------------------------
        total += 1
        print("\n[Test 1] Testing Cache-Aside Flow (Miss -> DB -> Set -> Hit)...")
        create_res = await client.post(
            "/links",
            json={"long_url": "https://example.com/module06-test-1"},
            headers=HEADERS_ORG_A,
        )
        assert create_res.status_code == 201, f"Expected 201, got {create_res.status_code}: {create_res.text}"
        link_data = create_res.json()
        code = link_data["code"]
        link_id = link_data["id"]

        # Verify initially not in cache (pure cache-aside)
        key = get_cache_key(code)
        r_client = await cache_module.ensure_redis()
        cached_init = await r_client.get(key)
        assert cached_init is None, f"Expected key {key} to be empty before first redirect"

        initial_misses = cache_metrics["misses"]
        initial_hits = cache_metrics["hits"]

        # First redirect: should be a Cache Miss -> query DB -> populate cache -> 307
        r1 = await client.get(f"/r/{code}")
        assert r1.status_code == 307, f"Expected 307, got {r1.status_code}"
        assert r1.headers["location"] == "https://example.com/module06-test-1"
        assert cache_metrics["misses"] == initial_misses + 1, f"Miss count did not increment: {cache_metrics}"

        # Verify key is now populated in Redis
        cached_after = await r_client.get(key)
        assert cached_after is not None, f"Expected key {key} to be populated in Redis"
        print(f"  -> Cache populated: {cached_after}")

        # Second redirect: should be a Cache Hit -> read Redis -> 307
        r2 = await client.get(f"/r/{code}")
        assert r2.status_code == 307, f"Expected 307, got {r2.status_code}"
        assert r2.headers["location"] == "https://example.com/module06-test-1"
        assert cache_metrics["hits"] == initial_hits + 1, f"Hit count did not increment: {cache_metrics}"
        print("  -> Cache-aside miss then hit confirmed successfully.")
        passed += 1

        # ---------------------------------------------------------
        # Test 2: Invalidation on Link Update (PATCH /links/{id})
        # ---------------------------------------------------------
        total += 1
        print("\n[Test 2] Testing Cache Invalidation on Link Update (PATCH)...")
        # Update target URL
        new_url = "https://example.com/module06-updated-url"
        patch_res = await client.patch(
            f"/links/{link_id}",
            json={"long_url": new_url},
            headers=HEADERS_ORG_A,
        )
        assert patch_res.status_code == 200, f"Expected 200, got {patch_res.status_code}: {patch_res.text}"
        assert patch_res.json()["long_url"] == new_url

        # Check that cache key was evicted
        cached_after_patch = await r_client.get(key)
        assert cached_after_patch is None, f"Expected key {key} to be evicted after PATCH"
        print("  -> Cache entry evicted after PATCH.")

        # Redirect should now fetch from DB and redirect to new URL
        r3 = await client.get(f"/r/{code}")
        assert r3.status_code == 307
        assert r3.headers["location"] == new_url
        print(f"  -> Redirect after update correctly routed to: {new_url}")
        passed += 1

        # ---------------------------------------------------------
        # Test 3: Invalidation on Link Deletion (DELETE /links/{id})
        # ---------------------------------------------------------
        total += 1
        print("\n[Test 3] Testing Cache Invalidation on Link Deletion (DELETE)...")
        # Verify cached again from previous redirect
        cached_before_del = await r_client.get(key)
        assert cached_before_del is not None

        del_res = await client.delete(f"/links/{link_id}", headers=HEADERS_ORG_A)
        assert del_res.status_code == 204

        # Check that cache key was evicted
        cached_after_del = await r_client.get(key)
        assert cached_after_del is None, f"Expected key {key} to be evicted after DELETE"
        print("  -> Cache entry evicted after DELETE.")

        # Redirect should now return 404
        r4 = await client.get(f"/r/{code}")
        assert r4.status_code == 404
        print("  -> Redirect after deletion correctly returned 404.")
        passed += 1

        # ---------------------------------------------------------
        # Test 4: Tenant Scoping & Isolation
        # ---------------------------------------------------------
        total += 1
        print("\n[Test 4] Testing Tenant Scoping & Isolation in Cache...")
        # Create link for Org A
        create_a = await client.post(
            "/links",
            json={"long_url": "https://tenant-a.com/dashboard"},
            headers=HEADERS_ORG_A,
        )
        assert create_a.status_code == 201
        link_a = create_a.json()
        code_a = link_a["code"]
        id_a = link_a["id"]

        # Populate cache by redirecting
        r_a = await client.get(f"/r/{code_a}")
        assert r_a.status_code == 307

        # Verify cached payload includes org_id
        cached_data = await get_redirect_target(code_a)
        assert cached_data is not None
        assert cached_data["org_id"] == "org_a"
        print(f"  -> Cache payload verified with org_id: {cached_data['org_id']}")

        # Org B attempts to PATCH Org A's link -> must be rejected with 404 (not owner)
        patch_b = await client.patch(
            f"/links/{id_a}",
            json={"long_url": "https://malicious.com"},
            headers=HEADERS_ORG_B,
        )
        assert patch_b.status_code == 404, f"Expected 404 for cross-tenant PATCH, got {patch_b.status_code}"

        # Org B attempts to DELETE Org A's link -> must be rejected with 404
        del_b = await client.delete(f"/links/{id_a}", headers=HEADERS_ORG_B)
        assert del_b.status_code == 404, f"Expected 404 for cross-tenant DELETE, got {del_b.status_code}"

        # Invalidate call with Org B context cannot evict Org A's entry
        inval_result = await invalidate_redirect_target(code_a, org_id="org_b")
        assert inval_result is False, "Cross-tenant invalidation should have been blocked"
        still_cached = await get_redirect_target(code_a)
        assert still_cached is not None, "Cache should not have been evicted by unauthorized tenant"
        print("  -> Cross-tenant mutation and eviction blocked successfully.")
        passed += 1

        # ---------------------------------------------------------
        # Test 5: Graceful Degradation (Redis Down Fallback to PostgreSQL)
        # ---------------------------------------------------------
        total += 1
        print("\n[Test 5] Testing Graceful Degradation (Redis Down Fallback)...")
        # Create a new link in PostgreSQL
        create_drill = await client.post(
            "/links",
            json={"long_url": "https://fallback.com/graceful-degradation"},
            headers=HEADERS_ORG_A,
        )
        assert create_drill.status_code == 201
        drill_code = create_drill.json()["code"]

        # Temporarily mock ensure_redis to return None to simulate Redis down
        orig_ensure = cache_module.ensure_redis

        async def fail_ensure():
            return None

        cache_module.ensure_redis = fail_ensure

        try:
            # Request redirect: Redis is down, but redirect MUST STILL SUCCEED via PostgreSQL
            r_down = await client.get(f"/r/{drill_code}")
            assert r_down.status_code == 307, f"Expected 307 fallback, got {r_down.status_code}"
            assert r_down.headers["location"] == "https://fallback.com/graceful-degradation"
            print("  -> Redirect succeeded via PostgreSQL fallback while Redis was unavailable.")
            passed += 1
        finally:
            # Restore ensure_redis
            cache_module.ensure_redis = orig_ensure

        # ---------------------------------------------------------
        # Test 6: Expired Link Handling in Cache
        # ---------------------------------------------------------
        total += 1
        print("\n[Test 6] Testing Link Expiration in Cache...")
        # 1. set_redirect_target rejects caching already-expired links
        exp_code = "exp001"
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        set_res = await set_redirect_target(
            code=exp_code,
            long_url="https://expired.example.com",
            ttl_seconds=10,
            org_id="org_a",
            expires_at=expired_time,
        )
        assert set_res is False, "Expired link should not be cached"
        exp_lookup = await get_redirect_target(exp_code)
        assert exp_lookup is None, "Expired cache entry should return None"

        # 2. get_redirect_target detects and purges expired entry if present
        import json
        key_exp = get_cache_key("exp002")
        await r_client.set(
            key_exp,
            json.dumps({
                "long_url": "https://expired2.example.com",
                "org_id": "org_a",
                "expires_at": expired_time.isoformat()
            })
        )
        exp_lookup2 = await get_redirect_target("exp002")
        assert exp_lookup2 is None, "Purged expired entry on read"
        print("  -> Expired cache entry correctly identified, rejected/purged, and returned None.")
        passed += 1

    await close_redis()
    print("\n" + "=" * 60)
    print(f"Module 06 Verification Complete: {passed}/{total} tests passed.")
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
