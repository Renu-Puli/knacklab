# Module 05 – STEP 4: VERIFY Responses

## Question 1: Why is leaking stack traces risky?

A stack trace can expose internal file paths, database queries, function names, framework details, and potentially sensitive configuration. Attackers can use this information to understand the application's internal structure and identify vulnerabilities.

In our URL shortener, if a PostgreSQL connection fails, the client should receive a generic HTTP 500 response with `INTERNAL_ERROR` and a request ID. The complete traceback must remain in secure server-side logs.

---

## Question 2: What is the difference between logs for debugging vs logs for auditing?

Debugging logs help developers identify and resolve technical problems. They contain diagnostic information such as exception details, request IDs, and error context.

Auditing logs record important system activities for accountability and security. They capture information such as who performed an action, what action occurred, when it happened, and its outcome.

In our URL shortener, a database failure is a debugging event, while recording that an organization created a short link is an auditing event.

---

## Question 3: What fields are essential for incident debugging?

Essential fields include:
- `timestamp`
- `request_id`
- log level
- `route`
- HTTP method
- `status_code`
- `latency_ms`
- error code
- server-side exception details

The request ID helps correlate a particular request across logs. API keys, passwords, tokens, and other sensitive information must be redacted.
