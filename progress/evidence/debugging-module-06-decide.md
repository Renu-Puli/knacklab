# Debugging & Incident Response — Module 06: Decide

**Track**: `debugging-incident-response`  
**Module**: 06 — Caching With Redis & Cache Invalidation Integrity  
**Step**: STEP 2 — DECIDE  
**Status**: COMPLETED  

---

## 1. Incident Hypothesis
- **Hypothesis**: The application implements read-through caching on `GET /r/{code}` with a 1-hour TTL, but fails to trigger cache invalidation (`DEL link:{code}`) during write operations (`PATCH /links/{id}` and `DELETE /links/{id}`).
- **Root Risk**: Stale data anomaly where the cache and database diverge for up to 3600 seconds, causing customer campaigns to route traffic to outdated or retired destination URLs.

---

## 2. Decision Options Considered

### Option A: Short TTL Only (e.g. 5 seconds)
- Retain cache-aside without active invalidation, but drastically lower the TTL from 1 hour to 5 seconds.
- **Tradeoff**: Drastically increases cache miss rates and database load under high traffic; does not solve the 5-second window of staleness.

### Option B: Cache-Aside with Event-Driven Invalidation & Tenant Scoping (Selected)
- **Decision**: `decisions.module_06.cache_strategy = "cache_aside"`
- **Twist Action**: `decisions.module_06.constraints_twist_action = "implement_now"`
- Keep 1-hour default TTL for high cache hit rates (>95%).
- Trigger immediate, atomic cache invalidation via `invalidate_redirect_target(link.code, org_id)` whenever a link is modified (`PATCH`) or removed (`DELETE`).
- Store `org_id` inside the cached payload to enforce organization scoping and verify that mutations cannot evict or poison foreign tenant keys.
- Preserve graceful degradation: if Redis is unreachable, redirect requests transparently fall back to PostgreSQL queries.

### Option C: Write-Through Caching
- Update PostgreSQL and immediately update the Redis cache key on every PATCH.
- **Tradeoff**: Increases write latency; requires two-phase error handling if the cache update fails while the DB commit succeeded. Eviction (Option B) is safer and simpler.

---

## 3. Decision Rationale
Option B (Cache-Aside with Immediate Eviction) guarantees immediate cache consistency upon database updates while keeping the read path fast, resilient, and tenant-isolated.
