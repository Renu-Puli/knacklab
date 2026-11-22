# Module 04: Authentication & Authorization — STEP 1: CONTEXT

## 1. Architectural Boundaries in URL Shortener (LinkOps)
In a production B2B multi-tenant URL Shortener, traffic patterns naturally diverge into two strictly separated planes:
1. **Public Traffic Plane**:
   - `GET /r/{code}`: High-throughput, read-heavy redirect resolution.
   - Must remain publicly accessible without requiring credentials or tokens so end-users clicking shared links are never blocked.
   - Protected against denial-of-service and short-code enumeration via IP-based sliding-window rate limiting (120 req/min) returning `HTTP 429 Too Many Requests`.
2. **Administrative & Tenant Management Plane**:
   - `POST /links`, `GET /links`, `GET /links/{id}`, `DELETE /links/{id}`, `GET /links/{id}/analytics`.
   - Requires explicit authentication (`X-API-Key` header) identifying the tenant (`Principal(principal_id, org_id)`).
   - Enforces strict multi-tenant authorization where callers access only links where `created_by == principal.org_id`.
   - Protected by API-key sliding-window rate limiting (30 req/min for link creation).

---

## 2. Threat Modeling & Failure Modes Without Authentication

### Q1: Name one endpoint that must stay public and why.
**The `GET /r/{code}` endpoint must remain public and unauthenticated.**
- *Rationale*: Anyone receiving a short link via email, SMS, or web must be redirected to the target destination without an account or API key. Requiring credentials would defeat the fundamental purpose of a URL shortener. Abuse is controlled via IP rate limiting rather than authentication.

### Q2: Name two endpoints that must be protected and what an attacker could do without protection.
1. **`POST /links` (Link Creation)**:
   - *Risk*: Without authentication, attackers can flood the service with spam, phishing redirects, or malware links, blacklisting the domain and exhausting database and storage resources.
2. **`GET /links` and `GET /links/{id}` (Link Listing & Inspection)**:
   - *Risk*: Without authentication and tenant scoping, any party can scrape private destination URLs, discover unreleased landing pages, access client analytics, or enumerate other organizations' internal link structures.

