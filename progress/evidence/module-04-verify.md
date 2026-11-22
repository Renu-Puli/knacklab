# Module 04 – STEP 4: VERIFY

## Verification Questions and Answers

### Q1. What is the difference between authentication and authorization?
Authentication verifies the identity of the application or organization making a request using its API key. Authorization checks what that authenticated organization is allowed to access or modify.

In our URL shortener, the API key identifies the organization (`principal_id` / `org_id`), and tenant-scoped authorization ensures that the organization can access only its own links (`created_by == principal.org_id`). Cross-tenant resource requests return `404 Not Found` (`decisions.module_04.not_owner_status = 404`) to prevent ID and short code enumeration.

### Q2. How do we revoke access if an API key or token leaks?
When an API key leaks, the administrator must revoke or disable the corresponding server-side key record or remove the registered hash. Since the server validates API keys against active hashed key records on every request, subsequent requests using the compromised key are immediately rejected with `HTTP 401 Unauthorized`. A replacement key can then be generated and issued.

Unlike stateless JWTs, API keys support instantaneous revocation without token propagation delays because their validity is checked against authoritative storage on every request. In contrast, stateless JWTs require additional architectural mechanisms—such as token blacklists/denylists, token versioning, or very short TTLs with refresh token rotation—to achieve early revocation.

### Q3. Why should the redirect endpoint remain public?
The `GET /r/{code}` endpoint must remain public because anyone receiving a shortened URL should be able to open it in a browser or application without needing an API key. Requiring authentication on redirects would break external access, prevent ordinary visitors from reaching shared destinations, and defeat the fundamental purpose of a URL shortener service.

Administrative operations—such as creating, listing, retrieving by ID, and deleting links—remain strictly protected by API key authentication and scoped to the tenant organization.
