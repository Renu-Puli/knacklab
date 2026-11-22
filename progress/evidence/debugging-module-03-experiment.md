# Module 03: Reproduction Science — STEP 4: EXPERIMENT

## 1. Experiment Overview & Boundaries
- **Objective**: Execute the synthetic reproduction harness (`scripts/repro_race.py`) under controlled conditions to test the Concurrency Hypothesis (Candidate 3).
- **Target**: Isolated synthetic link (`code='test-link'`, `id=913`, pointing to `https://example.com/synthetic-destination-...`, owned by `synthetic_tenant_repro`).
- **Data Safety**: Pure synthetic data; 0 production credentials, 0 customer tokens, 0 PII.
- **Concurrency**: Default concurrency level of 10 simultaneous requests.
- **Execution Transport**: In-process ASGI transport via `httpx.ASGITransport(app=app)`.

---

## 2. Empirical Execution Results

```text
[REPRO SETUP] Created synthetic link: code='test-link', id=913
======================================================================
MODULE 03: REPRODUCTION SCIENCE — SYNTHETIC REPRO HARNESS
Target Short Code : test-link
Concurrency Level : 10 simultaneous requests
Execution Mode    : ASGI In-Process Transport
======================================================================

--- Repro Run Summary ---
Total Requests          : 10
Successes (301/302/307) : 10
Server Errors (500)     : 0
Client Errors (4xx)     : 0
Exceptions / Network    : 0
Status Code Breakdown   : [307, 307, 307, 307, 307, 307, 307, 307, 307, 307]

[RESULT] No 500 errors observed in this run.
```

---

## 3. Analysis & Key Observations

1. **Response Distribution**:
   - 10 out of 10 requests completed with **HTTP 307 Temporary Redirect**.
   - **Zero HTTP 500 Internal Server Errors** occurred in this initial run.
   - **Zero unhandled exceptions** or request drops occurred.

2. **Architectural Trace & Telemetry**:
   - In `apps/api/app/routers/redirect.py`, click event recording is decoupled from the HTTP redirect path via `_dispatch_click_event()` (enqueuing to Celery).
   - Redis was offline during the test run (`bootcamp-redis` stopped), causing cache lookup fallback to PostgreSQL (`"Redis initialization failed ... Cache will run in fallback mode"`).
   - In accordance with resilience standards, enqueue failures logged a warning (`"Failed to enqueue click event for link 913: Error 10061 connecting to localhost:6379"`) without degrading public redirect availability.
   - In accordance with the explicit experimental boundaries, **zero failures are treated as valid empirical evidence**; no higher concurrency levels or code modifications were forced.
