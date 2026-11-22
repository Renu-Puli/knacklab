# Module 06 (Caching With Redis) — STEP 7: REFLECT

**Session ID**: 50AjqbAoaLqhp9Ff4JbN_  
**Date**: 2026-11-20  
**Status**: COMPLETED & REVIEWED  

---

## 1. Executive Summary & Decision Callback

In Module 06, we added distributed caching using Redis on the hot public redirect path (`GET /r/{code}`) of our B2B multi-tenant FastAPI URL shortener.

### Decision Recorded
- **Strategy**: Option A – Cache-Aside (`decisions.module_06.cache_strategy = cache_aside`).
- **Constraints Twist**: `org_scoping` implemented now (`decisions.module_06.constraints_twist_action = implement_now`).

### Architectural Tradeoff: Control vs. Responsibility
- **Why Cache-Aside**: Public redirects represent >99% of system traffic. Cache-aside ensures that PostgreSQL remains the single durable source of truth. Redis acts purely as an optimization layer. Writes (creating, updating, and deleting links) are not tightly coupled to Redis availability.
- **The Responsibility**: Cache-aside gives full control over cache population and TTL, but makes the application responsible for explicit invalidation on mutations. The bug encountered during the BREAK step (serving a stale redirect because invalidation was missing in `update_link`) is the canonical consequence of this model.

---

## 2. Knowledge Check Answers

### Q1. What core problem does this module solve in caching with Redis?
Caching solves the performance problem of repeatedly querying PostgreSQL for frequently accessed data. Redis caches popular redirect destinations, reducing database load and improving response speed. Cache misses fetch data from PostgreSQL and populate Redis, while Redis failures gracefully fall back to the database.

### Q2. Which decision in this module has the biggest impact, and why?
Choosing the Cache-Aside strategy had the biggest impact. It allowed us to control cache population, TTL, and invalidation while keeping PostgreSQL as the source of truth. However, it also introduced the responsibility of manually invalidating cache entries, which we experienced when a stale redirect was served during BREAK.

### Q3. What evidence proves the implementation works end-to-end?
The Module 06 verification and FIX tests demonstrate cache miss and hit behavior, invalidation after PATCH and DELETE, tenant isolation, expiration handling, and PostgreSQL fallback when Redis is unavailable. The targeted FIX reproduction passed all 8 checks and confirmed that after updating a link, the redirect returns the new destination instead of the stale cached URL.

---

## 3. Mini Practical Verification Evidence

Evidence captured from automated test suites (`verify_module_06.py` and `scripts/verify_module_06_fix.py`):

### A. Cache Hit on Second Redirect
```text
[Test 1] Testing Cache-Aside Flow (Miss -> DB -> Set -> Hit)...
POST /links completed with status 201 in 269.16ms (Short code: vmWOo58)
GET /r/vmWOo58 completed with status 307 in 161.37ms (Cache Miss -> DB query -> Cache populated)
  -> Cache populated: {"long_url": "https://example.com/module06-test-1", "org_id": "org_a", "link_id": 619, "expires_at": null}
GET /r/vmWOo58 completed with status 307 in 57.51ms (Cache Hit -> 0 DB queries, ~65% latency reduction)
  -> Cache-aside miss then hit confirmed successfully.
```

### B. Cache Invalidation on Update (PATCH)
```text
[Step 3 & 4] Sent PATCH /links/618:
  Status:       200 OK
  Returned URL: https://example.com/repaired-destination-v2-verified
  PostgreSQL verified: https://example.com/repaired-destination-v2-verified

[Step 5] Checking Redis cache key after PATCH:
  Key 'link:xH9yOyk' exists in Redis: False
  -> CONFIRMED: Cache entry was successfully evicted upon PATCH commit.
```

### C. Fresh Redirect Returned After Update
```text
[Step 6 & 7] Requesting public redirect GET /r/xH9yOyk after repair:
  HTTP Status Code: 307
  Location Header:  https://example.com/repaired-destination-v2-verified
  Expected URL:     https://example.com/repaired-destination-v2-verified
  -> CONFIRMED: Redirect points to the NEW updated destination!

[Step 8] Checking Redis cache key after subsequent redirect:
  Key 'link:xH9yOyk' repopulated with:
    long_url: https://example.com/repaired-destination-v2-verified
  -> CONFIRMED: Redis repopulated with updated destination URL.
```

### D. Redis-Down Graceful Fallback
```text
[Test 5] Testing Graceful Degradation (Redis Down Fallback)...
POST /links completed with status 201 (code: IZIIzBp)
Simulating Redis unavailable / connection timeout...
apps.api.cache WARNING: Redis unavailable or timed out. Falling back to DB.
GET /r/IZIIzBp completed with status 307 in 81.31ms
  -> Redirect succeeded via PostgreSQL fallback while Redis was unavailable.
  -> Zero 500 errors, zero dropped traffic.
```

---

## 4. Operator / SRE Audit: Remaining Risks & Mitigations

### 1. Concurrency Spikes & Cache Stampede (Thundering Herd)
- **Failure Mode**: When a viral short link's cache entry expires or is invalidated, hundreds or thousands of concurrent redirect requests simultaneously experience a cache miss and flood PostgreSQL with identical queries.
- **Production Impact**: Database connection pool exhaustion, CPU spikes, and severe tail-latency degradation across all API endpoints.
- **Production Mitigations**:
  1. *Single-flight Request Coalescing*: Mutex/promise locking so that only the first request performs the database read while concurrent requests wait and share the populated result.
  2. *Probabilistic Early Expiration (XFetch)*: Recomputing and refreshing cache entries before strict TTL expiration based on traffic volume and read compute time.
  3. *Connection Limits & Bounded Fallbacks*: Enforcing strict semaphore limits on fallback database queries during high-concurrency periods.

### 2. Dual-Write Inconsistency (DB–Redis Asynchrony)
- **Failure Mode**: PostgreSQL updates commit successfully, but the subsequent Redis eviction fails (e.g. transient Redis timeout, network partition, or worker crash before eviction).
- **Production Impact**: Redis continues serving stale redirect destinations until the cache key expires.
- **Production Mitigations**:
  1. *Bounded TTL*: Every key has a mandatory TTL (capped at 3,600s or link expiration), ensuring bounded inconsistency even under worst-case network partitions.
  2. *Transactional Outbox / Invalidation Queue*: In upcoming modules, publishing link update events to an asynchronous outbox table or message broker with guaranteed at-least-once delivery to ensure reliable cache eviction retries.
