# Debugging & Incident Response — Module 06: Context

**Track**: `debugging-incident-response`  
**Module**: 06 — Caching With Redis & Cache Invalidation Integrity  
**Step**: STEP 1 — CONTEXT  
**Status**: COMPLETED  

---

## 1. Incident Overview & Scenario
As LinkOps scaled, database read traffic on the public redirect route (`GET /r/{code}`) increased exponentially. To alleviate database connection pool pressure and reduce response latency from 50ms to <5ms, a Redis caching layer was introduced using the **Cache-Aside** pattern.

However, incident reports from enterprise customers revealed a critical consistency failure:
- When an organization updated the destination URL of an active marketing link (via `PATCH /links/{id}`), the API reported success (`HTTP 200 OK`) and PostgreSQL committed the new URL.
- Despite the successful update, visitors clicking the short link continued to be redirected to the **old, stale destination URL** for up to an hour (until the TTL expired).
- In some cases, deleted links (`DELETE /links/{id}`) continued redirecting visitors instead of returning `HTTP 404 Not Found`.

---

## 2. Core Questions & Answers

### Q1. If Redis is down, should redirects fail or fall back to DB? Why?
Redirects must fall back to PostgreSQL:
- **Why**: PostgreSQL is the authoritative system of record and single source of truth for short links.
- Redis serves strictly as a performance optimization and caching acceleration layer.
- Under the graceful degradation principles established in Module 05, the failure or downtime of a caching layer must never render the core public redirect functionality (`GET /r/{code}`) unavailable.

### Q2. Name one place you must invalidate cache to avoid stale redirects.
Cache invalidation is strictly required whenever a link is updated (`PATCH /links/{id}`) or deleted (`DELETE /links/{id}`):
- **Why**: If an organization changes `long_url` or deletes a link, the active Redis cache entry for `link:{code}` must be immediately evicted (`DEL`).
- Without explicit invalidation upon mutation, incoming traffic continues serving stale destination URLs directly from memory, violating data correctness.

---

## 3. Constraints Twist: Organization Scoping (`org_scoping`)
- **Product Scenario**: `b2b_multi_tenant`
- **Twist Type**: `org_scoping` (`decisions.module_06.constraints_twist_type = "org_scoping"`)
- **Action**: Option A – `implement_now` (`decisions.module_06.constraints_twist_action = "implement_now"`)

### Rationale:
In a multi-tenant B2B platform, cache entries must store tenant metadata (`org_id`), and cache eviction routines must enforce tenant boundaries. Tenant A must never be permitted to evict, poison, or overwrite Tenant B's cached redirects. Implementing tenant-scoped caching now prevents cross-tenant data leakage and avoids complex retrofits in production.
