# LinkOps Railway Deployment Guide

## 1. Architecture Overview
LinkOps requires 4 services in Railway:
1. **API Service (`web`)**:
   - Source: Repository root
   - Builder: Dockerfile (or Nixpacks)
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
   - Healthcheck: `/health`
2. **PostgreSQL Database (`database`)**:
   - Official Railway PostgreSQL Plugin (PostgreSQL 16)
   - Connection URL: `${{Postgres.DATABASE_URL}}`
3. **Redis (`redis`)**:
   - Official Railway Redis Plugin
   - Connection URL: `${{Redis.REDIS_URL}}`
4. **Celery Worker Service (`worker`)**:
   - Source: Same repository root
   - Start Command: `celery -A app.worker.celery_app worker --loglevel=INFO -P solo`

## 2. Environment Variables Required

### For API (`web`):
- `DATABASE_URL`: `${{Postgres.DATABASE_URL}}`
- `REDIS_URL`: `${{Redis.REDIS_URL}}`
- `CELERY_BROKER_URL`: `${{Redis.REDIS_URL}}`
- `PORT`: `${{PORT}}` (or default 8000)
- `LOG_LEVEL`: `INFO`
- `API_KEY_A`: `<Generate strong 32-char hex string, e.g. api_key_primary_live>`
- `API_KEY_B`: `<Generate strong 32-char hex string, e.g. api_key_secondary_live>`
- `JWT_SECRET`: `<Generate strong 32-char hex string>`
- `RETENTION_DAYS`: `30`

### For Celery Worker (`worker`):
- `DATABASE_URL`: `${{Postgres.DATABASE_URL}}`
- `REDIS_URL`: `${{Redis.REDIS_URL}}`
- `CELERY_BROKER_URL`: `${{Redis.REDIS_URL}}`
- `LOG_LEVEL`: `INFO`
- `RETENTION_DAYS`: `30`
