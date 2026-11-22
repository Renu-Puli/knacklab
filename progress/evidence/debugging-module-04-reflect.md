# Module 04: Authentication & Authorization — STEP 5: REFLECT

## 1. Executive Summary & Root Cause
In Module 04, we investigated the fragile boundary between **fail-fast deployment configuration** and **runtime authentication security**. 

- **Root Cause**: The application configuration model (`Settings` in `app/config.py`) specified an explicit, mandatory environment alias `api_key_a: str = Field(..., alias="API_KEY_PRIMARY")`. However, deployment manifests and local `.env` files provided `API_KEY_A`. During container boot, Pydantic's `BaseSettings` failed validation, crashing the service before port binding.
- **Remediation**: Leveraging Pydantic v2's `AliasChoices` permitted dual-alias resolution (`validation_alias=AliasChoices("API_KEY_PRIMARY", "API_KEY_A", "api_key_a")`). This eliminated the deployment mismatch while preserving fail-fast validation for mandatory infrastructure variables.

---

## 2. Decision Callback (Closing the DECIDE Loop)
- In Step 2 (DECIDE), we rejected Option A (forcing deployment manifests to adopt `API_KEY_PRIMARY`) because it would break existing test automation, staging configurations, and developer environments.
- We selected Option B (`AliasChoices`), which establishes a graceful transition path: the application now supports both legacy conventions (`API_KEY_A`) and new infrastructure naming standards (`API_KEY_PRIMARY`) with zero breaking changes.

---

## 3. Security Boundaries & Architecture Preserved
1. **Constant-Time Cryptographic Comparison**: API keys are hashed with SHA-256 and compared using `secrets.compare_digest` in `APIKeyRegistry`, eliminating timing side-channels.
2. **Anti-Enumeration Contract (HTTP 404)**: Accessing a resource owned by another tenant returns `404 Not Found` rather than `403 Forbidden`, preventing attackers from enumerating valid link IDs across tenants.
3. **Public Redirect Contract (HTTP 307)**: `GET /r/{code}` remains completely unauthenticated and public.
4. **Sliding-Window Rate Limiting (HTTP 429)**: Link creation is throttled at 30 req/min per API key, and redirects are throttled at 120 req/min per IP, returning standard `Retry-After` headers.
5. **Regression Safety**: All test suites across previous modules (Module 01 sorting, Module 02 log injection & timezones, Module 03 QueuePool decoupling, Module 07 task idempotency) passed with zero regressions.

---

## 4. Lessons Learned
- **Configuration as Code Must Support Evolution**: Naming conventions in infrastructure inevitably change between development, staging, and multi-cloud production. Hardcoding rigid aliases without transition choices causes preventable outages.
- **Rate Limiting Architecture**: In-memory rate limiting works well for single-instance testing, but distributed deployments require shared state (Redis) to enforce rate limits across multiple web workers.

