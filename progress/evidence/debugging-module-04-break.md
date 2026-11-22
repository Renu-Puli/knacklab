# Module 04: Authentication & Authorization — STEP 3: BREAK

## 1. Controlled Reproduction of Configuration Alias Failure
To deterministically reproduce the deployment incident, the application settings were evaluated against an environment providing `API_KEY_A` while the configuration schema declared a mandatory alias `api_key_a: str = Field(..., alias="API_KEY_PRIMARY")`.

---

## 2. Empirical Failure Evidence

```text
CAPTURED EXCEPTION TYPE: ValidationError
RAW EXCEPTION:
 1 validation error for BreakSettings
API_KEY_PRIMARY
  Field required [type=missing, input_value={'port': '8000', 'DATABASE_URL': 'postgres://postgres:postgres@localhost:5432/upsk_sdf', 'mongodb_uri': 'mongodb://localhost:27017/upsk_sdf', 'redis_url': 'redis://localhost:6379', 'jwt_secret': 'replace-me-locally', 'api_key_a': 'replace-me-locally', 'api_key_b': 'replace-me-locally', 'retention_days': 30, 'celery_broker_url': 'redis://localhost:6379/0', 'log_level': 'INFO'}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.14/v/missing
```

When intercepted by the startup safety guard in `apps/api/app/config.py`:
```text
RuntimeError: Startup Configuration Error: Invalid or missing environment configuration.
1 validation error for Settings
API_KEY_PRIMARY
  Field required
```

---

## 3. Diagnostic Differentiation from Other Failures
- **Distinguished from Database Outage**: A database failure raises `psycopg.OperationalError` during database pool initialization (`engine.connect()`), which occurs downstream after configuration loading.
- **Distinguished from Port Collision**: A port collision raises `socket.error: [Errno 98/10048] Address already in use` when Uvicorn attempts socket binding.
- **Root Cause Confirmed**: The failure is purely static schema validation: Pydantic strictly matched the single alias `API_KEY_PRIMARY` and rejected runtime initialization because the environment defined `API_KEY_A`.

