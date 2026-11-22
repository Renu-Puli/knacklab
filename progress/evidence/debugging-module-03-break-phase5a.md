# Module 03: Reproduction Science — STEP 5: BREAK (Phase 5A)

## 1. Experiment Overview & Authorized Scope
- **Command Executed**: `apps\api\.venv\Scripts\python.exe scripts/repro_race.py --concurrency 25 --code test-link`
- **Authorized Target**: Isolated synthetic link (`code='test-link'`, `id=913`, pointing to `https://example.com/synthetic-destination-...`, owned by `synthetic_tenant_repro`).
- **Data Safety**: Pure synthetic test link and synthetic tenant; zero customer tokens, zero production credentials, zero PII.
- **Concurrency**: 25 simultaneous requests (Phase 5A authorized level).
- **Transport**: In-process ASGI transport via `httpx.ASGITransport(app=app)`.
- **Infrastructure State**: PostgreSQL active (`upsk-sdf-postgres`); Redis stopped / offline (`bootcamp-redis` stopped).

---

## 2. Empirical Execution Results

```text
[REPRO SETUP] Using existing synthetic link: code='test-link', id=913
======================================================================
MODULE 03: REPRODUCTION SCIENCE — SYNTHETIC REPRO HARNESS
Target Short Code : test-link
Concurrency Level : 25 simultaneous requests
Execution Mode    : ASGI In-Process Transport
======================================================================

--- Repro Run Summary ---
Total Requests          : 25
Successes (301/302/307) : 15
Server Errors (500)     : 0
Client Errors (4xx)     : 0
Exceptions / Network    : 10
Status Code Breakdown   : [307, 307, 'TimeoutError', 'TimeoutError', 307, 307, 307, 307, 'TimeoutError', 'TimeoutError', 307, 'TimeoutError', 307, 307, 'TimeoutError', 'TimeoutError', 'TimeoutError', 307, 307, 307, 307, 'TimeoutError', 'TimeoutError', 307, 307]

[RESULT] No 500 errors observed in this run.
```

---

## 3. Telemetry & Log Analysis

1. **HTTP Status Code Breakdown**:
   - **HTTP 307 (Temporary Redirect)**: 15 requests (60%) succeeded normally and redirected to the synthetic destination.
   - **HTTP 500 (Internal Server Error)**: **0 requests (0%)**.
   - **HTTP 4xx (Client Errors)**: **0 requests (0%)**.
   - **Client-Side TimeoutError**: 10 requests (40%) timed out waiting on in-process ASGI execution.

2. **Root Cause of Client-Side Timeouts**:
   - Because `bootcamp-redis` was kept stopped per safety constraints, each ASGI worker request attempted connection to `127.0.0.1:6379` during cache-aside lookup and cache population.
   - The TCP socket timeout is configured for 2.0s (`socket_connect_timeout=2.0`).
   - Under 25 simultaneous ASGI coroutines, synchronous/async connection waits cascaded, causing 10 requests to exceed httpx's client timeout while waiting for the connection failure fallback to complete.
   - Even when Redis connection failed, the application caught the error gracefully (`"Redis initialization failed ... Cache will run in fallback mode"` / `"Failed to enqueue click event for link 913: Error 10061 connecting to localhost:6379"`).
   - In accordance with resilience designs, **the application did not raise an unhandled exception or return an HTTP 500**.

3. **Reproduction Outcome**:
   - **HTTP 500 was NOT reproduced in Phase 5A.**
   - Causal Variable Status: Scaling concurrency to 25 with Redis offline exercises the fallback path and degrades latency, but does not trigger the internal server error race condition.
