# Module 05 – DECIDE: Error Handling Strategy

**Selected Option**: **Option B: Graceful Degradation**  
**Decision Key**: `decisions.module_05.error_strategy = graceful`

---

## Architectural Reasoning

Our URL shortener's primary function is redirecting users to their destination URLs. Temporary failures in supporting infrastructure such as Redis caching or the asynchronous analytics job queue should not needlessly disrupt this core user-facing functionality.

### Q1. For redirect, should we return 500 or fall back to the database when cache fails?
We should fall back to PostgreSQL when Redis/cache is unavailable:
- PostgreSQL remains the authoritative source of truth for short links.
- If Redis fails, times out, or drops connection, the application catches the cache exception, falls back to querying PostgreSQL directly, and returns the expected `307 Temporary Redirect`.
- If PostgreSQL itself is also unavailable, the system safely returns an appropriate HTTP 500 response with a generic error and a `request_id`, rather than pretending the redirect succeeded.

### Q2. What happens if the analytics job queue is down?
Analytics processing must not block or fail the primary redirect operation:
- The redirect pathway must continue returning 307 redirects to users even when the analytics queue/broker is degraded or offline.
- Queue failures must be captured in server-side structured logs with warning/error levels and correlated with the `request_id`.
- A resilient retry or durable recovery mechanism (e.g., local buffer, dead-letter queue, or outbox pattern) should be used where supported.
- The application must never falsely report that an analytics event was successfully recorded if it was dropped.

---

## Architectural Boundary Clarification

Graceful degradation strictly applies to **non-critical runtime dependencies** (caching, background telemetry, metrics).  
In contrast, **security validation, authentication, and critical environment configuration** remain strictly **fail-fast**:
- Missing or malformed credentials fail fast with 401 Unauthorized.
- Cross-tenant requests fail fast with 404 Not Found.
- Corrupted or invalid environment configurations fail fast at application boot time to protect system integrity.
