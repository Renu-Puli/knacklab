# Debugging & Incident Response — Module 07: Context

**Track**: `debugging-incident-response`  
**Module**: 07 — Background Jobs & Analytics Decoupling  
**Step**: STEP 1 — CONTEXT  
**Status**: COMPLETED  

---

## 1. Incident Overview & Scenario
In high-concurrency production deployments of LinkOps, the public redirect endpoint (`GET /r/{code}`) represents the hot path (>99% of total system throughput).

Prior to Module 07, recording click analytics (`ClickEvent` timestamp, user agent, referrer, IP hash) was executed synchronously inside the redirect handler. Under traffic surges:
- Synchronous database writes introduced latency spikes and database lock contention.
- PostgreSQL connection pool exhaustion (reproduced in Module 03) threatened redirect availability.
- A database slow-down or blip immediately caused customer redirects to stall or fail.

To protect redirect speed and availability, analytics telemetry must be completely decoupled from the HTTP response loop using an asynchronous background job queue (Celery + Redis).

---

## 2. Core Questions & Answers

### Q1. If the queue is down, what should the redirect do?
The redirect must **succeed normally** (returning `HTTP 307 Temporary Redirect` with the appropriate `Location` header) and must **never fail, hang, or return HTTP 500**.
- **Rationale**: Public redirects are the core user-facing deliverable; analytics is secondary telemetry.
- When pushing an event to the queue fails (e.g., Redis broker unreachable), the API intercepts the exception, logs a warning with the correlation `request_id`, and completes the redirect immediately.

### Q2. What is your idempotency key for a click event?
The idempotency key is the unique event identifier: `click_event_id` (derived from `click:{request_id}`).
- **Rationale**: In asynchronous distributed queues, at-least-once message delivery and worker network retries can cause the same task payload to be redelivered.
- By enforcing uniqueness on `click_event_id` at the database layer (or via deduplication in worker logic), retried tasks are detected and ignored, preventing duplicate click records and inflated customer metrics.
