# Module 04: Authentication & Authorization – Decisions & Threat Model

## 1. Authentication Strategy Decision
- **Auth Strategy**: Option A (API Key Authentication)
- **Configuration Key**: `decisions.module_04.auth_method = "api_key"`
- **Rationale**:
  API keys provide simple and effective service-to-service authentication for our B2B multi-tenant URL Shortener API. Each API key can be associated with a specific organization/principal, allowing the application to identify the tenant and enforce strict data isolation. API keys also support immediate revocation through database validation and make it easier to apply rate limits per organization. This approach has less implementation complexity than JWT and is suitable for our current API architecture.

## 2. Authorization "Not Owner" Status Decision
- **Status Code**: `404 Not Found`
- **Configuration Key**: `decisions.module_04.not_owner_status = 404`
- **Rationale**:
  When one organization attempts to access another organization's link by ID, returning `HTTP 404 Not Found` instead of `HTTP 403 Forbidden` effectively hides the existence of resources belonging to other tenants. This minimizes resource enumeration attacks, timing side-channels, and cross-tenant information leakage.

## 3. Threat Model
We are protecting our multi-tenant URL Shortener against:
1. **Unauthorized link creation**: Attackers creating spam/phishing links without an account.
2. **Cross-tenant data access**: Unauthorized users reading, updating, or deleting other organizations' links.
3. **Short-code and ID enumeration**: Probing link IDs or short codes to discover internal resources.
4. **Resource exhaustion / Denial of Service (DoS)**: High-frequency API calls exhausting database connections or CPU.
5. **API key theft / misuse**: Compromised credentials being used indefinitely without revocation.

### Mitigations in BUILD:
- **Admin Protection**: All link management endpoints (`POST /links`, `GET /links`, `GET /links/{id}`, `DELETE /links/{id}`) require an `X-API-Key` header mapped to a `principal_id` (organization).
- **Public Redirect**: `GET /r/{code}` remains public and unauthenticated.
- **Tenant Scoping & 404 on Cross-Tenant Access**: Any attempt to read or manipulate a link outside the authenticated tenant returns `404 Not Found`.
- **Rate Limiting**:
  - `create_link_per_min = 30`
  - `redirect_per_min = 120`
  - Throttled requests receive `HTTP 429 Too Many Requests`.
