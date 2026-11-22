# Debugging & Incident Response — Module 05: Decide

**Track**: `debugging-incident-response`  
**Module**: 05 — Error Handling, Transaction Integrity & Observability  
**Step**: STEP 2 — DECIDE  
**Status**: COMPLETED  

---

## 1. Incident Hypothesis
- **Hypothesis**: The application code in `create_link` catches generic database exceptions during `db.commit()` and swallows them, returning a fake success response (`HTTP 201 Created` with a fabricated ID) instead of aborting the operation and propagating a standardized error to the client.
- **Root Risk**: Violates ACID transaction integrity, results in silent data loss, and breaks customer trust by claiming resources exist when they were never written to disk.

---

## 2. Options Considered

### Option A: Fail-Fast Everywhere (Strict Non-Degraded)
- Treat every external dependency (PostgreSQL, Redis, Celery) as strictly critical.
- If Redis cache fails or analytics queue drops a connection during redirect, immediately return HTTP 500.
- **Tradeoff**: Unnecessarily reduces redirect availability when secondary/non-critical services degrade.

### Option B: Architectural Graceful Degradation with Transaction Boundaries (Selected)
- **Decision**: `decisions.module_05.error_strategy = "graceful"`
- Apply **graceful degradation** strictly to **non-critical runtime dependencies** (e.g., Redis caching miss falls back to PostgreSQL; analytics queue failure logs a warning without breaking public 307 redirects).
- Enforce **strict fail-fast transactional integrity** for **critical stateful operations** (database inserts, updates, deletes, and security authentication).
- If a database commit fails during `create_link`, explicitly execute `db.rollback()` and re-raise the exception to the global unhandled exception handler, returning `HTTP 500 Internal Server Error` with an opaque error envelope and `request_id`.
- Standardize all error responses to include `error: {code, message, request_id}` and set `X-Request-ID`.

### Option C: In-Memory Buffering on DB Failure
- If PostgreSQL fails, store links in memory and retry in the background.
- **Tradeoff**: High risk of data loss on container restart, complex distributed consistency issues, and violates tenant durability guarantees.

---

## 3. Decision Rationale
Option B provides the optimal balance of high availability for public redirect hot-paths while guaranteeing absolute transactional correctness for administrative writes. It completely eliminates silent data loss.
