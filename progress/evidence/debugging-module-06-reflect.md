# Debugging & Incident Response — Module 06: Reflect

**Track**: `debugging-incident-response`  
**Module**: 06 — Caching With Redis & Cache Invalidation Integrity  
**Step**: STEP 5 — REFLECT  
**Status**: COMPLETED  

---

## 1. Decision Callback & Architectural Tradeoffs
In the DECIDE step, **Option B (Cache-Aside with Active Invalidation & Org Scoping)** was selected (`decisions.module_06.cache_strategy = "cache_aside"`, `constraints_twist_action = "implement_now"`).

The BREAK exercise demonstrated why relying exclusively on cache TTLs is dangerous in production:
- With a 1-hour TTL, updating a link's destination URL creates a 60-minute window of inconsistency where clients receive stale destination redirects.
- In contrast, immediate cache eviction upon DB commit guarantees read-your-own-writes consistency.
- Implementing organization scoping directly in cache payloads ensures that Tenant A cannot evict or manipulate Tenant B's cached redirects.

---

## 2. Key Questions & Incident Analysis

### Q1. If Redis is down, should redirects fail or fall back to DB? Why?
Redirects must fall back to PostgreSQL. Caching is an availability and latency optimization, not an authoritative datastore. If Redis is down, PostgreSQL remains completely operational and can serve all valid redirects.

### Q2. Name one place you must invalidate cache to avoid stale redirects.
Every link update (`PATCH /links/{id}`) and deletion (`DELETE /links/{id}`). If the underlying destination changes, any cached entry for `link:{code}` must be evicted immediately.

### Q3. What evidence proves the implementation works end-to-end?
- `apps/api/scripts/verify_module_06_fix.py`: **8/8 checks passed**:
  * Step 1: Created short link.
  * Step 2: Warmed Redis cache via `GET /r/{code}`.
  * Step 3: Sent `PATCH /links/{id}` with new destination.
  * Step 4: Verified PostgreSQL committed the new URL.
  * Step 5: Confirmed Redis cache entry was immediately evicted (`assert cached is None`).
  * Step 6 & 7: Verified `GET /r/{code}` returned `HTTP 307` pointing to the **new** updated destination.
  * Step 8: Confirmed Redis repopulated with the updated destination on the subsequent request.
- `apps/api/verify_module_06.py`: **6/6 automated checks passed**:
  * Test 1: Cache-Aside Flow (Miss -> DB -> Set -> Hit).
  * Test 2: Invalidation on Link Update (PATCH).
  * Test 3: Invalidation on Link Deletion (DELETE).
  * Test 4: Tenant Scoping & Isolation in Cache (cross-tenant eviction blocked).
  * Test 5: Graceful Degradation (Redis Down Fallback to PostgreSQL).
  * Test 6: Link Expiration in Cache (expired entries rejected and purged).

---

## 3. Remaining Production Risks & Mitigations
- **Cache Stampede / Thundering Herd**: If a high-traffic link is invalidated, thousands of concurrent requests could hit PostgreSQL simultaneously.
- **Mitigation**: Implement singleflight mutex locking or soft-TTL background re-warming for popular links.
