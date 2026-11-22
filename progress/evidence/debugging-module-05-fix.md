# Debugging & Incident Response — Module 05: Fix

**Track**: `debugging-incident-response`  
**Module**: 05 — Error Handling, Transaction Integrity & Observability  
**Step**: STEP 4 — FIX  
**Status**: COMPLETED  

---

## 1. Root Cause Analysis
In `apps/api/app/routers/links.py`, the `create_link` function caught all generic exceptions during `db.commit()` and returned a dummy response instead of rolling back the session and propagating the error:

```python
# BROKEN PATTERN:
except Exception:
    db.rollback()
    return LinkResponse(id=999999, code=code, ...)  # Silent failure / fake success!
```

---

## 2. Minimal Fix Implemented
1. **Transaction Boundary & Exception Propagation**:
   In `apps/api/app/routers/links.py`:
   ```python
   try:
       db.add(link)
       db.commit()
       db.refresh(link)
       break
   except IntegrityError:
       db.rollback()
       if attempt == max_retries - 1:
           raise HTTPException(
               status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
               detail="Failed to generate a unique short code. Please try again."
           )
   except Exception:
       db.rollback()
       raise  # Propagate to global exception handler
   ```
2. **Standardized Error Envelope & Stack Trace Suppression**:
   In `apps/api/app/errors.py`:
   - Global unhandled exception handler catches all `Exception` instances.
   - Logs full diagnostic traceback server-side correlated with `request_id`.
   - Returns clean RFC-compliant error JSON to client:
     ```json
     {
       "error": {
         "code": "INTERNAL_ERROR",
         "message": "Internal server error",
         "request_id": "req_..."
       }
     }
     ```
   - Sets `X-Request-ID` response header matching `error.request_id`.
   - Never exposes internal file paths, SQL statements, or Python tracebacks to the caller.
3. **Graceful Degradation for Non-Critical Operations**:
   - `GET /r/{code}`: If Redis is unavailable, falls back to PostgreSQL and serves `HTTP 307`.
   - Background click tracking: If Redis broker is down, intercepts exception, logs warning with `request_id`, and allows the `HTTP 307` redirect to succeed without interruption.

---

## 3. Backups Created
- `apps/api/app/routers/links.py.bak`
