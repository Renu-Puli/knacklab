# Module 04: Authentication & Authorization — STEP 4: FIX

## 1. Implementation Summary
In `apps/api/app/config.py`, the configuration schema was updated to leverage Pydantic v2's `AliasChoices` for flexible, backward-compatible environment variable resolution:

- **Modified File**: [`apps/api/app/config.py`](file:///C:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/app/config.py)
- **Backup File**: [`apps/api/app/config.py.m04.bak`](file:///C:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/app/config.py.m04.bak)

### Code Diff:
```python
from pydantic import Field, field_validator, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ...
    api_key_a: str = Field(
        default="",
        validation_alias=AliasChoices("API_KEY_PRIMARY", "API_KEY_A", "api_key_a")
    )
    api_key_b: str = Field(
        default="",
        validation_alias=AliasChoices("API_KEY_SECONDARY", "API_KEY_B", "api_key_b")
    )
```

---

## 2. Test Execution & Verification

### Verification Suite: `apps/api/scripts/verify_module_04.py`
The full 13-check regression and security suite was executed against the running service stack:

| Test ID | Test Scope | Status | Result / Output |
| :--- | :--- | :---: | :--- |
| **TEST 1** | `POST /links` without API key | **PASS** | `HTTP 401 Unauthorized` |
| **TEST 2** | `GET /links` without API key | **PASS** | `HTTP 401 Unauthorized` |
| **TEST 3** | Admin endpoint with invalid API key | **PASS** | `HTTP 401 Unauthorized` |
| **TEST 4** | Valid `API_KEY_A` creates link | **PASS** | `HTTP 201 Created` (`created_by: "org_a"`) |
| **TEST 5** | Strict tenant isolation | **PASS** | Org A sees only Org A links; Org B sees only Org B links |
| **TEST 6** | Cross-tenant access (`GET /links/{id_a}` by Tenant B) | **PASS** | `HTTP 404 Not Found` (anti-enumeration) |
| **TEST 7** | Cross-tenant deletion (`DELETE /links/{id_a}` by Tenant B) | **PASS** | `HTTP 404 Not Found` |
| **TEST 8** | Public redirect (`GET /r/{code}`) without auth | **PASS** | `HTTP 307 Temporary Redirect` |
| **TEST 9** | Unknown short code redirect | **PASS** | `HTTP 404 Not Found` |
| **TEST 10** | Expired short link redirect | **PASS** | `HTTP 410 Gone` |
| **TEST 11** | Create-link rate limiting (30/min per key) | **PASS** | Throttled on request 31 with `HTTP 429` & `Retry-After` |
| **TEST 12** | Redirect rate limiting (120/min per IP) | **PASS** | Throttled on request 121 with `HTTP 429` & `Retry-After` |
| **TEST 13A** | URL validation security checks | **PASS** | Rejects `javascript:`, data URIs, and control chars |
| **TEST 13B** | Click event tracking persistence | **PASS** | Click events verified in PostgreSQL |

**Overall Verification Result**: `13/13 Checks Passed (100%)`.

