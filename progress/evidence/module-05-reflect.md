# Module 05 – STEP 7: REFLECT

## 1. Chosen Error Strategy & Architectural Implications
**Selected Strategy**: **Option B – Graceful Degradation**  
`decisions.module_05.error_strategy = "graceful"`

### Reflection on Tradeoffs & Architectural Boundaries
Graceful degradation improves overall service availability by ensuring that transient failures in non-critical supporting dependencies do not disrupt core user-facing functionality. In our URL shortener, if click analytics logging or Redis caching becomes degraded or unavailable, the application falls back safely and continues serving HTTP 307 temporary redirects to destination URLs.

However, graceful degradation must strictly never be misapplied to critical operations (such as data persistence or security authentication). If PostgreSQL fails to commit a new link during creation, the application must safely roll back the transaction, propagate the exception, and return a standardized HTTP 500 response. 

The Module 05 BREAK exercise demonstrated this exact danger: attempting to apply graceful degradation to a failed database write by swallowing the exception and returning HTTP 201 Created caused silent data loss, generating "phantom" short links that failed with HTTP 404 when followed.

---

## 2. One Logging Rule to Follow
**Rule**: **Mandatory Secret Redaction & Request ID Correlation**  
*Never log raw API keys, passwords, bearer tokens, connection strings, or sensitive personal data. Every request must be assigned a validated or cryptographically safe correlation ID (`request_id`), and server logs must bind this ID to all audit events and error traces so incidents can be diagnosed rapidly without exposing credentials.*

---

## 3. Comprehension Questions

### Q1. What core problem does this module solve in error handling and logging?
This module ensures that application errors are handled safely, predictably, and consistently across client and server boundaries. Clients receive clean, uniform error envelopes without stack trace leakage, while engineers receive correlated, structured JSON logs that enable fast incident root-cause analysis without exposing confidential credentials or private system internals.

### Q2. Which decision in this module has the biggest impact, and why?
Choosing Graceful Degradation (Option B) has the biggest impact on service resilience. It decouples high-volume public redirects from secondary systems (like Redis and analytics queues), preventing cascade outages. At the same time, defining strict boundaries ensures that critical database failures remain loud, visible, and fail-safe with HTTP 500 rather than falsely reporting success.

### Q3. What evidence proves the implementation works end-to-end?
- **33/33 automated checks passed** across all 5 verification suites.
- **HTTP 422 Validation Errors**: Invalid payloads return standardized error envelopes with code `VALIDATION_ERROR` and human-readable field messages.
- **HTTP 500 Server Errors**: Unexpected database exceptions return opaque error envelopes with code `INTERNAL_ERROR` and generic message `"Internal server error"`, completely suppressing Python tracebacks.
- **Header Correlation**: `X-Request-ID` is present on 100% of responses and matches the JSON envelope's `request_id`.
- **Secret Redaction**: Sentinel `DO_NOT_LOG_ME_123` was audited across server logs and had 0 occurrences.
- **Transaction Rollback**: Failed database transactions roll back cleanly without persisting orphan rows or fake IDs.
- **Core Functionality**: Valid link creations persist to PostgreSQL, and public redirects return HTTP 307.

---

## 4. Mini Practical Task: Reproducible Evidence

### A. Request ID Propagation
- **Command**:
  ```powershell
  curl.exe -i -H "X-API-Key: API_KEY_A" -H "X-Request-ID: trace-audit-uuid-456" -H "Content-Type: application/json" -d '{"long_url": "invalid-url"}' http://localhost:8000/api/v1/links
  ```
- **Output**:
  ```http
  HTTP/1.1 422 Unprocessable Entity
  Content-Type: application/json
  X-Request-ID: trace-audit-uuid-456

  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Validation failed: long_url: Invalid or prohibited URL scheme ''. Only 'http' and 'https' are allowed.",
      "request_id": "trace-audit-uuid-456"
    }
  }
  ```
  *Proof: Response header `X-Request-ID` and JSON envelope `error.request_id` match identically.*

### B. Safe HTTP 500 Error Envelope & Traceback Suppression
- **Test Execution**: `apps/api/scripts/reproduce_break.py` (simulating database commit timeout).
- **Client Response**:
  ```http
  HTTP/1.1 500 Internal Server Error
  Content-Type: application/json
  X-Request-ID: req_fix_verify_db_fail_500

  {
    "error": {
      "code": "INTERNAL_ERROR",
      "message": "Internal server error",
      "request_id": "req_fix_verify_db_fail_500"
    }
  }
  ```
- **Traceback Suppression**: 0 occurrences of `Traceback`, `RuntimeError`, or internal file paths in client JSON.
- **Server-Side Log**: Recorded complete traceback correlated with `req_fix_verify_db_fail_500` in server logs only.

### C. Secret Redaction Audit
- **Test Request**: Header `X-API-Key: DO_NOT_LOG_ME_123` sent to `/api/v1/links`.
- **Response**: HTTP 401 Unauthorized.
- **Captured Server Log Record**:
  ```json
  {"timestamp": "2026-11-18T10:10:48.012345+00:00", "level": "INFO", "logger": "apps.api", "message": "GET /api/v1/links completed with status 401 in 14.23ms", "request_id": "req_sentinel_audit_check", "route": "/api/v1/links", "status_code": 401, "latency_ms": 14.23, "method": "GET"}
  ```
- **Log Audit**: String `DO_NOT_LOG_ME_123` verified **100% ABSENT** (0 occurrences). Raw authentication headers are never written to disk or stdout.

---

## 5. Remaining Production Risk & Mitigation
- **Risk**: Database connection pool exhaustion or queries that hang indefinitely under load can saturate worker threads, leading to silent latency degradation or unresponsive containers.
- **Mitigation Strategy**:
  1. Configure explicit database pool timeouts (`pool_timeout=5`, `connect_timeout=3`) and statement execution timeouts.
  2. Implement active readiness checks (`GET /health`) probing database connectivity before routing ingress traffic.
  3. Emit structured latency metrics (`latency_ms`) on all request logs to trigger automated alerting when 95th-percentile latency spikes.
