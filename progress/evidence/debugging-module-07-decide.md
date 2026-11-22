# Debugging & Incident Response — Module 07: Decide

**Track**: `debugging-incident-response`  
**Module**: 07 — Background Jobs & Analytics Decoupling  
**Step**: STEP 2 — DECIDE  
**Status**: COMPLETED  

---

## 1. Incident Hypothesis
- **Hypothesis**: Offloading click tracking to background Celery tasks decouples the redirect hot path, but worker task processing without idempotency guarantees creates duplicate records whenever tasks are retried or redelivered.
- **Root Risk**: Analytics double-counting, corrupted billing metrics, and database table bloat from redundant rows.

---

## 2. Decision Options Considered

### Option A: Synchronous Database Inserts (Status Quo)
- Keep click tracking synchronous in the redirect endpoint.
- **Tradeoff**: Degrades redirect latency, consumes DB connection pool capacity, and violates availability isolation.

### Option B: Asynchronous Queue with Idempotent Consumer & Data Retention (Selected)
- **Decision**: `decisions.module_07.jobs_strategy = "async_queue"`
- **Retention Decision**: `decisions.module_07.retention_days = 30`
- The API handler pushes a lightweight event dictionary to Redis queue and returns `HTTP 307` immediately (<10ms).
- A Celery worker processes tasks asynchronously and executes idempotent `ON CONFLICT (click_event_id) DO NOTHING` inserts into PostgreSQL.
- Redelivered tasks return `{"status": "deduplicated"}` without inserting new rows.
- A periodic maintenance job (`purge_expired_clicks_task`) automatically prunes telemetry older than 30 days to bound storage growth.
- IP addresses are hashed with SHA-256 before queue dispatch to satisfy privacy compliance.

### Option C: Fire-and-Forget In-Memory Threads
- Use `BackgroundTasks` in FastAPI memory without Redis or Celery.
- **Tradeoff**: In-memory tasks are lost if the web container restarts; no backpressure control under severe spikes.

---

## 3. Decision Rationale
Option B provides enterprise-grade throughput and fault isolation. The redirect hot path is completely protected from database latency, and idempotent workers ensure telemetry accuracy even across network retries.
