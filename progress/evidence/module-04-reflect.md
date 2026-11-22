# Module 04: Authentication & Authorization – REFLECT

## Comprehension Questions & Answers

### Q1. What core problem does this module solve in authentication and authorization?
This module solves the problem of securing administrative operations and protecting data between different organizations in a multi-tenant URL shortener.

Authentication verifies the identity of the organization using its API key. Authorization ensures that the organization can access and manage only its own links.

Tenant isolation is enforced using `Link.created_by == principal.org_id`. Administrative endpoints (`POST /links`, `GET /links`, `GET /links/{id}`, `DELETE /links/{id}`) require authentication, while the public redirect endpoint `GET /r/{code}` remains accessible without authentication.

### Q2. Which decision in this module has the biggest impact, and why?
The most important decision was choosing Option A: API Key Authentication instead of JWT.

API keys are suitable for our B2B service-to-service URL shortener because they provide a simple way to identify organizations and support centralized key revocation.

Another important decision was returning HTTP 404 instead of 403 for cross-tenant resource requests. This prevents attackers from discovering whether another organization's link exists and reduces resource enumeration risks.

### Q3. What evidence proves the implementation works end-to-end?
The final regression verification achieved 23/23 passing checks across four test suites (`reproduce_break.py`, `verify_module_04.py`, `run_fix_test.py`, and `verify_module_03.py`).

Evidence includes:
- Unauthenticated administrative requests return 401 Unauthorized.
- Invalid API keys are rejected.
- Cross-tenant access and deletion attempts return 404 Not Found.
- Public redirects work without authentication and return 307 Temporary Redirect.
- Expired links return 410 Gone.
- Rate limiting returns 429 Too Many Requests with Retry-After headers.
- Click tracking records events in PostgreSQL asynchronously.
- Previous Module 03 functionality remains intact.

## Chosen Authentication Method & Reason
API Key Authentication was selected because it is simple and suitable for B2B service-to-service communication. It identifies organizations and supports centralized revocation when a key is compromised.

## Key Security Practice Learned
API keys should never be stored or compared as plaintext. Our implementation uses SHA-256 hashing and constant-time comparison with `secrets.compare_digest()` to eliminate timing side-channel attacks.

Additionally, tenant-scoped authorization and returning 404 for cross-tenant resources prevent information leakage and resource probing.
