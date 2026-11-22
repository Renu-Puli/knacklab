# Module 03: VERIFY Questions & Answers

## Q1. Why do we keep redirect routes separate from admin API routes?
We keep redirect routes separate from admin API routes to maintain a clear separation between public and private operations. Redirect routes are publicly accessible, while admin API routes are used to create, manage, and view links. This separation prevents route conflicts, improves security, and makes the application easier to maintain and scale.

## Q2. What status code should a validation error return and why?
A validation error should return HTTP 422 – Unprocessable Entity (or 400 Bad Request depending on client framing). It indicates that the server understands the content type and syntax of the request entity, but the semantic data does not satisfy validation rules (e.g. scheme not in allowlist, control characters present, or malicious pseudo-schemes).

## Q3. What should happen if a link is expired?
If a link is expired, the application should not redirect the user to its destination. It should return HTTP 410 – Gone (or a clear error page/status), indicating that the target resource was intentionally configured with an expiry time that has passed and is permanently no longer available.

