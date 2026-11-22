# Module 07 – STEP 1: CONTEXT (Background Jobs & Analytics)

**Date**: 2026-11-20  
**Module**: 07 — Background Jobs & Analytics  
**Step**: STEP 1 — CONTEXT  
**Status**: COMPLETED  

---

## 1. Core Problem: Separating the Hot Path from Analytical Processing

In a production URL shortener, the public redirect path (`GET /r/{code}`) is the **hot path**:
- Traffic volume is massive (>99% of total requests).
- End users expect sub-millisecond response latency.
- System availability must remain near 100%.

In contrast, click analytics recording (`ClickEvent`: timestamp, IP address, user agent, referer) is **telemetry and business intelligence**:
- It requires write operations (I/O, database row locking, index updates).
- Under high concurrency, executing synchronous database writes on every single redirect severely degrades redirect throughput, exhausts database connection pools, and introduces latency spikes.
- **Fundamental Rule**: Analytics is useful, but it is never worth breaking redirect speed or redirect availability.

---

## 2. Synchronous vs. Asynchronous Analytics Trade-offs

| Dimension | Synchronous (Current Baseline) | Asynchronous via Queue (Module 07 Goal) |
| :--- | :--- | :--- |
| **Redirect Latency** | High: Blocked on PostgreSQL write and transaction commit. | Ultra-low: Pushes lightweight event to queue in memory; returns HTTP 307 immediately. |
| **System Complexity** | Low: Simple in-process database call; no extra services. | Moderate/High: Requires broker/queue, worker process, serialization, and message schema. |
| **Database Load** | Severe: 1 DB write per redirect; surges directly impact the database. | Controlled: Workers can batch insert records (`executemany`) and smooth traffic spikes (buffer absorption). |
| **Failure Modes** | DB latency directly slows down redirects; DB crash threatens redirect uptime. | Queue failure or worker failure can cause dropped events or backpressure if not isolated. |
| **Retry & Consistency** | Immediate error or drop; retries happen on the HTTP request. | At-least-once delivery introduces duplicate risks if retries are not idempotent. |

---

## 3. Micro-Exercise Questions & Answers

### Q1. If the queue is down, what should the redirect do?
**Answer**:
The redirect must **succeed normally** (returning `307 Temporary Redirect` with the appropriate `Location` header) and must **never fail, hang, or return HTTP 500**.

**Architectural Rationale**:
- Public redirects are the primary customer-facing deliverable; analytics is non-critical secondary observability.
- When pushing an event to the queue fails (e.g. connection timeout or queue service down), the API must intercept the exception, log a warning with the correlation `request_id`, and complete the redirect immediately.
- Optional degraded handling: buffer events in a bounded local in-memory circular buffer or drop telemetry under backpressure, but under zero circumstances allow queue failure to block the user.

---

### Q2. What is your idempotency key for a click event?
**Answer**:
The idempotency key is the unique request identifier:  
`idempotency_key = f"click:{request_id}"` (or `request_id` directly, e.g., `req_<uuid4>`).

**Architectural Rationale**:
- In our FastAPI service, every incoming HTTP request receives a cryptographically unique `request_id` from `RequestIdMiddleware` (`req_...`).
- When a worker pulls a click event from the queue, network interruptions or worker crashes during processing can trigger queue re-deliveries (at-least-once delivery semantics).
- By recording `request_id` on the `click_events` table with a unique constraint (or checking an atomic Redis deduplication set with TTL), repeated deliveries of the same redirect click event are detected and discarded as duplicates.
- This prevents double-counting analytics, ensuring metrics and billing data remain accurate even during worker retries.

---

## 4. Connection to Our B2B Multi-Tenant Architecture

1. **Current Baseline**:
   - In Module 03, synchronous click tracking was implemented in `redirect.py` with try/except DB resilience.
   - In Module 06, Redis caching accelerated destination lookups, but synchronous database inserts on clicks remain an I/O bottleneck.
2. **Upcoming Module 07 Architecture**:
   - Decouple the redirect handler from PostgreSQL writes using asynchronous queueing (e.g. Redis Streams or background worker).
   - Enforce tenant isolation in analytics: click events retain `link_id` and organizational scoping (`created_by`), ensuring analytics queries remain tenant-isolated.
   - Build worker consumers that batch process click events safely with idempotency protection.
