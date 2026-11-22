# Module 02 — STEP 3: BUILD Evidence & Completion Report

**Track:** Debugging & Incident Response  
**Module:** 02 — Reading Logs Like a Story  
**Step:** 3 — BUILD  

---

## 1. Bug #3: Log Level Misconfigured

### Diagnosis
- The logging subsystem did not respect or read the `LOG_LEVEL` environment variable.
- In `apps/api/app/config.py`, `Settings` omitted `log_level`.
- In `apps/api/app/logging_config.py`, `configure_logging()` hardcoded `level: int = logging.INFO` as a parameter default.
- In `apps/api/app/main.py`, `configure_logging()` was called with zero arguments.
- Consequently, if an operator or `.env` file set `LOG_LEVEL=WARN`, `INFO`-level request completion logs were silenced, causing `404` and `500` errors to appear in isolation without request context.

### Implementation
1. **[apps/api/app/config.py](file:///c:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/app/config.py):** Added `log_level: str = Field(default="INFO", alias="LOG_LEVEL")` to `Settings`.
2. **[apps/api/.env](file:///c:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/.env):** Appended `LOG_LEVEL=INFO`.
3. **[apps/api/app/logging_config.py](file:///c:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/app/logging_config.py):** Implemented `resolve_log_level()` to safely resolve string and int log levels (including `WARN`, `FATAL`, and case-insensitive values) with a safe fallback to `logging.INFO`. Updated `configure_logging()` to set both root and logger (`apps.api`) levels.
4. **[apps/api/app/main.py](file:///c:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/app/main.py):** Updated entrypoint to pass `settings.log_level` to `configure_logging(level=settings.log_level)`.

### Verification
- Unit and integration tests in `scripts/verify_bug_03_fix.py` verified:
  - String parsing: `DEBUG`, `INFO`, `WARN`, `WARNING`, `ERROR`, `CRITICAL`, and `INVALID` fallback.
  - Stream filtering: Under `INFO`, requests emit complete structured JSON logs with `request_id`, `route`, `status_code`, `latency_ms`. Under `WARN`, `INFO` logs are suppressed while `WARNING` and `ERROR` are emitted. Under `DEBUG`, debug logs are emitted.
  - Request flow: `POST /links` (201), `GET /r/{code}` (307), `GET /r/nonexistent` (404) all succeed as expected.

---

## 2. Bug #4: Timestamp Timezone Mismatch

### Diagnosis
- Investigated user report claiming links created near midnight return 404 for several hours.
- Verified live system configuration:
  - PostgreSQL timezone: `Etc/UTC`.
  - Database schema: `created_at` and `expires_at` are `timestamp with time zone`.
  - Log timestamps: `datetime.now(timezone.utc)` (explicit ISO 8601 UTC).
  - Time delta between application clock and PostgreSQL `SELECT now()`: 15 ms.
  - Redirect lookup (`redirect.py`): Queries strictly on `Link.code == code`; contains no `created_at` or `NOW()` time boundary.
- **Empirical test:** Inserted a test link created at `2026-11-21 23:59:00+00:00` (1 minute prior to midnight UTC) and immediately resolved it via `/r/{code}`:
  - Returned HTTP `307 Temporary Redirect` immediately.
  - The reported 404 defect could not be reproduced because the system was already properly aligned in UTC.
- **Defensive hardening identified:** In `apps/api/app/schemas/link.py`, `validate_future_datetime()` validated naive datetimes against UTC, but returned naive `v` unchanged instead of the normalized timezone-aware object.

### Implementation
- **[apps/api/app/schemas/link.py](file:///c:/Users/Windows/OneDrive/Desktop/Knack_labs/apps/api/app/schemas/link.py):** Updated `validate_future_datetime()` to return `v_normalized = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)`, ensuring naive inputs are returned as explicit timezone-aware UTC objects for persistence.

### Verification
- Tested in `scripts/verify_bug_04_fix.py`:
  - Timezone-aware UTC datetimes handled properly.
  - Timezone-aware non-UTC datetimes retain exact instant.
  - Naive future datetimes normalized to UTC with `tzinfo=timezone.utc`.
  - Naive past datetimes rejected.
  - Future expiration allows redirect (307); expired links return 410 Gone.

---

## 3. Regression Suite Verification
- `scripts/run_fix_test.py`: Module 03 redirect, expiration, and analytics resilience tests **ALL PASSED**.
- `scripts/verify_module_01_fix.py`: Module 01 pagination stability and concurrent write tests **ALL PASSED**.
