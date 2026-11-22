# Module 06 – STEP 2: DECIDE (Cache Strategy)

**Selected Choice**: **Option A – Cache-Aside (Lazy Loading)**  
**Decision Key**: `decisions.module_06.cache_strategy = "cache_aside"`

---

## Architectural Reasoning

Our B2B URL Shortener is dominated by high-volume, read-heavy redirect traffic. Cache-aside (lazy loading) is the optimal strategy because:
1. **Targeted Caching**: Only links that actually receive traffic are cached, avoiding memory waste on created links that are rarely or never clicked.
2. **Resilience**: The application checks Redis first. On a cache miss, it queries PostgreSQL (the authoritative source of truth), writes the resolved destination to Redis, and executes the redirect.
3. **Availability Fallback**: If Redis crashes, experiences network partition, or times out, the application falls back gracefully to PostgreSQL without interrupting public redirects.

---

## Probing Questions & Architectural Strategy

### 1. What happens on cache miss?
- Query PostgreSQL for the short code using the authoritative link table.
- If the link exists and is active (not expired), populate Redis with the short-to-long URL mapping and proceed with the HTTP 307 temporary redirect.
- If the link does not exist, return HTTP 404 Not Found (and optionally cache a brief negative lookup to guard against cache stampedes / brute-force code enumeration).

### 2. What happens on update/delete?
- Update or delete the link in the PostgreSQL database first within a transaction.
- Once the database commit succeeds, actively invalidate (delete) the corresponding Redis cache entry.
- Ensure all cache mutations and keys are scoped to the authenticated tenant to prevent cross-tenant cache eviction or pollution.

### 3. How do we avoid serving stale URLs?
- **Active Invalidation**: Immediately delete the Redis key upon link update, expiration modification, or deletion.
- **Time-to-Live (TTL)**: Assign an explicit TTL (e.g., 3600 seconds) to cached entries as a defensive backstop against missed invalidation events.
- **Tenant Scoping**: Structure Redis cache keys with clear namespace prefixes (`link:{code}`) while ensuring administrative cache controls strictly respect tenant boundaries.

### 4. Non-Blocking Graceful Degradation
Redis operates as a non-blocking performance optimization. Under no circumstances should Redis failure, connection timeout, or unavailability block public redirect requests (`GET /r/{code}`) or cause 500 errors. When Redis is unavailable, the system logs the issue and falls back transparently to PostgreSQL.
