# Debugging & Incident Response — Module 05: Context

**Track**: `debugging-incident-response`  
**Module**: 05 — Error Handling, Transaction Integrity & Observability  
**Step**: STEP 1 — CONTEXT  
**Status**: COMPLETED  

---

## 1. Incident Overview & Scenario
In LinkOps (a B2B multi-tenant URL shortener), customers reported a critical data integrity bug:
- Organization admins created short links via `POST /api/v1/links` and received an immediate `HTTP 201 Created` response containing the short code and URL metadata.
- However, when end users immediately attempted to follow the short link (`GET /r/{code}`), the system returned `HTTP 404 Not Found`.
- An investigation of the database revealed that no row was ever committed to the `links` table in PostgreSQL.
- The failure was diagnosed as an anti-pattern: an overly broad exception handler caught a database error during link creation, fabricated a dummy response (`id=999999`), and returned HTTP 201 Created instead of rolling back and propagating the error.

---

## 2. Core Questions & Answers

### Q1. What information should a 500 response include, and what must it never include?
A 500 Internal Server Error response should contain:
- Standard HTTP status code: `500`.
- A safe, generic, RFC-compliant error envelope with an error code (e.g. `INTERNAL_ERROR`).
- A human-readable safe message: `"Internal server error"`.
- A unique correlation identifier: `request_id` (also delivered via `X-Request-ID` response header).

It must **never** include:
- Raw Python stack traces or internal exception classes.
- Database connection strings, SQL queries, or schema table names.
- Hostnames, container IDs, internal IP addresses, or file paths.
- Credentials, secrets, or API tokens.

### Q2. If a customer reports an issue, what is the single piece of data you want in the client response so you can find the exact logs?
The **Request ID** (`request_id` / `correlation_id`).  
By returning `request_id` in the client JSON response and in the `X-Request-ID` HTTP header, customer support and on-call engineers can instantly query server-side structured logs to locate the exact trace, timestamps, and error context without exposing internal details to the client.

---

## 3. Scope & Objectives
1. Eliminate swallowed exceptions and false-positive HTTP success responses.
2. Enforce explicit database transaction boundaries (`session.rollback()` on error and re-raising to global handlers).
3. Standardize error responses into uniform RFC 7807/9457 JSON envelopes across 4xx and 5xx errors.
4. Suppress stack traces from client responses while logging full tracebacks securely server-side.
5. Propagate and correlate `request_id` throughout all middleware, handlers, and response headers.
