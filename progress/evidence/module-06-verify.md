# Module 06 – STEP 4: VERIFY Responses

## Question 1: Why is cache invalidation hard?
In Cache-Aside, the application updates PostgreSQL and then invalidates Redis. These are two separate operations across heterogeneous systems, so they are not atomic. If the PostgreSQL commit succeeds but Redis invalidation fails because of a network partition, timeout, or Redis outage, the old cached URL remains in Redis. Public visitors may continue receiving redirects to the stale destination. 

TTL (Time-To-Live) is essential because it bounds the maximum lifetime of stale cache entries and guarantees that the cache will eventually refresh from PostgreSQL even when explicit invalidation fails. In our URL shortener, a failed invalidation can leave an outdated redirect cached for up to the configured TTL of one hour.

## Question 2: What's the risk of caching auth-protected data? (Multi-Tenant Cache Isolation & Stampedes)
In a B2B multi-tenant system, cache data and operations must strictly respect tenant boundaries. Unscoped cache keys or global invalidation endpoints can lead to severe security and compliance vulnerabilities:
1. **Cross-Tenant Information Leakage**: If private or tenant-specific metadata is cached with shared or guessable keys, another tenant could read or probe cached items belonging to a different organization.
2. **Unauthorized Cache Invalidation (Denial-of-Service / Cache Stampede)**: If tenant context is omitted during eviction, Tenant B could maliciously evict Tenant A's cached entries, forcing repeated database lookups and inducing a cache stampede on PostgreSQL.
3. **Data Contamination**: Caching authenticated responses without tenant scoping can cause Tenant A's user session or authorization context to be served to Tenant B.

In our implementation, `org_id` is stored directly in the cached payload, and `invalidate_redirect_target` explicitly validates that the requesting tenant owns the resource before allowing eviction. Furthermore, public redirects rely only on globally unique short codes, keeping admin operations strictly isolated.

Additionally, to prevent **cache stampedes** when popular keys expire under heavy concurrency, production systems employ mutex locking (single-flight deduplication), probabilistic early expiration (e.g. XFetch), and background pre-warming.

## Question 3: What should we do if Redis is unavailable?
If Redis is down or unreachable, the application must practice **Graceful Degradation**:
1. **Non-Blocking Fallback**: Public redirects (`GET /r/{code}`) must not fail with HTTP 500. The application should catch Redis connection and socket timeouts, log a structured diagnostic warning correlated with the request ID, and fall back directly to PostgreSQL as the authoritative source of truth.
2. **Strict Timeouts**: Strict connection timeouts (<= 2s) and socket timeouts (<= 1s) must be enforced so that a struggling or partitioned Redis node does not exhaust API worker threads or spike request latencies.
3. **Write Isolation**: Link creation, updates, and deletes must still succeed in PostgreSQL even if Redis is unreachable, relying on TTL expiration once Redis recovers.
