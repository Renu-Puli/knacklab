# Module 07 – STEP 4: VERIFY (Background Jobs & Analytics)

**Module**: 07 – Background Jobs & Analytics  
**Step**: STEP 4: VERIFY  
**Date**: 2026-11-20  

---

## 1. Official Knowledge Check Questions & Candidate Responses

### Q1: Why do retries create duplicate processing risk?
**Candidate Answer**:
Retries create duplicate processing risk because the worker may successfully save the click event in PostgreSQL but crash before acknowledging the task. Since Redis/Celery doesn't receive the ACK, it assumes the task was not completed and retries it. The same event may then be processed again, creating duplicate click records unless idempotency is implemented.

**Technical Evaluation**:
- **At-Least-Once Delivery**: With `task_acks_late=True`, task acknowledgment happens strictly after worker execution.
- **Non-Atomic Operations**: The PostgreSQL commit and Redis `ACK` are two independent network operations without distributed transactions (2PC). If the worker crashes, is OOM-killed, or loses network after the commit but before sending the `ACK`, Redis re-delivers the task to another worker.
- **Risk**: Without idempotency, redelivery results in duplicate rows, inflated analytics, and corrupted metrics.

---

### Q2: What is an idempotency key in this context?
**Candidate Answer**:
In our implementation, the idempotency key is `click_event_id`, generated as `click_{request_id}` for each redirect request. This key is passed along with the Celery task and stored in PostgreSQL. The database has a unique constraint on this key, and the worker uses `INSERT ... ON CONFLICT DO NOTHING`. If the same task is retried, the key remains the same, so the database ignores the duplicate insertion. This prevents duplicate click records and double-counting analytics.

**Technical Evaluation**:
- **Deterministic Derivation**: `click_event_id` is created on the redirect hot path using `request.state.request_id` (a cryptographically unique UUID generated per HTTP request).
- **Stable Payload**: Retries and redeliveries carry the identical `click_event_id`.
- **Database Enforcement**: PostgreSQL enforces a `UNIQUE INDEX` on `click_events.click_event_id`.
- **Deduplication Logic**: The Celery task executes `INSERT INTO click_events (...) ON CONFLICT (click_event_id) DO NOTHING RETURNING id`. Redelivered events are dropped silently at the database layer with zero duplicates.

---

### Q3: What should happen if analytics fails: block redirect or degrade?
**Candidate Answer**:
If analytics fails, the system should degrade gracefully instead of blocking or failing the redirect. The end user must still receive the HTTP 307 redirect to the original destination because redirecting is the core business function of our URL shortener, while analytics is a non-critical background task. In our implementation, analytics enqueueing is handled asynchronously using Celery. If queue submission fails, the exception is caught and logged, but the redirect still succeeds with HTTP 307. This keeps the service available even when Redis or the analytics infrastructure is unavailable. Analytics may be lost under our best-effort policy, but the user experience and core functionality are preserved.

**Technical Evaluation**:
- **Availability Prioritization**: Core business availability (HTTP 307 redirect) takes precedence over operational telemetry.
- **Fault Isolation**: Enqueueing (`record_click_event_task.delay(...)`) is wrapped in a guarded `try...except` block in `app/routers/redirect.py`.
- **Graceful Degradation**: If Redis or Celery is down, the exception is captured, a warning is logged with the request correlation ID, and the response immediately returns HTTP 307 with the correct `Location` header. The user never experiences an HTTP 500 or latency spike due to background system failures.

---

## 2. Verification Test Evidence Cross-Reference

| Topic | Verification Test | Result |
| :--- | :--- | :--- |
| **At-Least-Once Replay** | `verify_module_07.py` [Test 3] | Verified: replaying payload with existing `click_event_id` returns `deduplicated` status and leaves DB row count unchanged. |
| **Idempotency Key Integrity** | `verify_module_07.py` [Test 2 & 3] | Verified: unique constraint enforced; duplicate inserts ignored via `ON CONFLICT DO NOTHING`. |
| **Graceful Degradation** | `verify_module_07.py` [Test 5] | Verified: simulated Redis queue outage returns HTTP 307 without error or latency degradation. |
| **Privacy Compliance** | `verify_module_07.py` [Test 4] | Verified: only SHA-256 `ip_hash` stored; raw client IP is never persisted. |
| **Tenant Scoping** | `verify_module_07.py` [Test 7] | Verified: cross-tenant access to analytics returns HTTP 404 (anti-enumeration). |
| **Retention Purge** | `verify_module_07.py` [Test 9] | Verified: clicks older than 30 days are purged while keeping recent clicks and parent links intact. |
