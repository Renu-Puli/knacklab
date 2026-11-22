# Module 06 – STEP 1: CONTEXT (Caching With Redis)

## 1. Micro-Exercise Questions & Answers

### Q1. If Redis is down, should redirects fail or fall back to DB? Why?
If Redis is down, redirects must fall back to PostgreSQL.  
**Why**: PostgreSQL is the authoritative system of record and source of truth for short links. Redis serves strictly as a caching optimization layer to accelerate response times and reduce database read load under high volume. Under graceful degradation principles established in Module 05, the failure or unavailability of a caching layer must never render the core public redirect functionality (`GET /r/{code}`) unavailable.

### Q2. Name one place you must invalidate cache to avoid stale redirects.
Cache invalidation is strictly required whenever an existing short link is updated or deleted by its owning organization.  
**Why**: If an organization modifies the `long_url` target or deletes an existing link, any active Redis cache entry for that `code` must be evicted or invalidated immediately (e.g., via `DEL` or cache overwrite). Otherwise, incoming traffic will continue serving stale cached redirect destinations from memory, violating data correctness.

---

## 2. Constraints Change (Twist): Organization Scoping

### Scenario Configuration
- **Product Scenario**: `b2b_multi_tenant`
- **Twist Type**: `org_scoping` (`decisions.module_06.constraints_twist_type = "org_scoping"`)
- **Action**: Option A – `implement_now` (`decisions.module_06.constraints_twist_action = "implement_now"`)

### Architectural Reasoning
Organization scoping must be enforced end-to-end across every layer of the application architecture, including cache key namespaces and analytics pipelines. Tenant identity (`org_id` / `tenant_id`) derived from the authenticated API key must be bound to all relevant cache and operational paths. Cache structures must ensure strict multi-tenant isolation, guaranteeing that one organization can never access, evict, poison, or leak another organization's cached data. Implementing tenant-scoped caching now prevents critical cross-tenant data leakage vulnerabilities and avoids expensive, risky architectural retrofits in production.

### Prediction If Deferred
If organization scoping in caching is deferred:
1. Cache keys lacking tenant prefixes or tenancy boundaries could result in cross-tenant data collision, cache poisoning, or inadvertent disclosure where Tenant B receives Tenant A's cached metadata or administrative cache states.
2. Analytics and administrative cache lookups would fail to preserve tenant isolation guarantees, breaking the security boundary established in Module 04.
