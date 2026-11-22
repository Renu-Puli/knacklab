# Module 05 – Context: Error Handling & Logging

## Q1. What information should a 500 response include, and what must it never include?

A 500 Internal Server Error response should contain:
- Standard HTTP status code: 500.
- A safe, generic error message such as "Internal server error".
- A unique request identifier (`request_id` or `trace_id`).
- A stable application error code such as `INTERNAL_ERROR`.
- The request ID should also be returned through the `X-Request-ID` response header.

It must never expose:
- Raw Python stack traces or internal exception messages.
- Database error details or SQL queries.
- Environment variables, passwords, API keys, or connection strings.
- Internal IP addresses or private network topology.

Detailed exception information should be recorded only in access-controlled server-side structured logs and correlated using the request ID.

## Q2. If a customer reports an issue, what is the single piece of data you want in the client response so you can find the exact logs?

The most important information is the unique Request ID (`request_id` or `correlation_id`).

It should be included in both the response JSON and the `X-Request-ID` header. Engineers can search structured logs using this identifier to find the corresponding request lifecycle and investigate the internal exception.

Request IDs should be safely generated or validated rather than blindly trusting arbitrary client-supplied values.
