# Debugging & Incident Response — Module 05: Reflect

**Track**: `debugging-incident-response`  
**Module**: 05 — Error Handling, Transaction Integrity & Observability  
**Step**: STEP 5 — REFLECT  
**Status**: COMPLETED  

---

## 1. Decision Callback & Architectural Tradeoffs
In the DECIDE step, **Option B (Graceful Degradation with Transactional Boundaries)** was selected (`decisions.module_05.error_strategy = "graceful"`).

The BREAK exercise highlighted why boundary separation is critical:
- Misapplying "graceful degradation" to stateful database writes by swallowing exceptions and returning HTTP 201 caused silent data loss.
- Non-critical components (caching, background telemetry) benefit from graceful fallback because failure does not corrupt data.
- Stateful components (database transactions, authentication) must strictly fail fast and fail visibly.

---

## 2. Key Questions & Incident Analysis

### Q1. What core problem does this module solve in error handling and logging?
It enforces strict separation between client-facing error envelopes and server-side diagnostic observability. Clients receive predictable, safe, sanitized error payloads with correlation IDs, while engineers get full tracebacks and contextual structured logs without exposing sensitive system internals.

### Q2. Which decision has the biggest impact, and why?
The decision to enforce explicit transaction rollback and re-raise unhandled exceptions. This ensures the database session is never left in an aborted or dirty state and eliminates false-success responses.

### Q3. What evidence proves the implementation works end-to-end?
- `apps/api/scripts/reproduce_break.py`: Passed both normal persistence (HTTP 201 + verified in PostgreSQL) and database failure propagation (HTTP 500 + `INTERNAL_ERROR` + zero tracebacks).
- `apps/api/verify_module_05.py`: 9/9 automated checks passed:
  * Test A: Validation error returns 422 with safe envelope and `X-Request-ID`.
  * Test A2: Legacy `/links` returns 422 with identical safe envelope.
  * Test B: Simulated database crash returns generic HTTP 500 with zero leaked tracebacks.
  * Test C: Sensitive sentinel `DO_NOT_LOG_ME_123` verified 100% absent from logs.
  * Test D1 & D2: Valid `X-Request-ID` preserved; malicious headers sanitized.
  * Test E1-E4: Safe envelopes verified for 401, 404, 410, and 429 status codes.

---

## 3. One Logging Rule to Follow
**Mandatory Secret Redaction & Correlation**:  
Never write raw secrets, API keys, passwords, bearer tokens, or sensitive user data to logs. Always attach a validated correlation ID (`request_id`) to every request log so that issues can be diagnosed sub-second without compromising security.
