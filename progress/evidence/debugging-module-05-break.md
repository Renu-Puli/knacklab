# Debugging & Incident Response — Module 05: Break

**Track**: `debugging-incident-response`  
**Module**: 05 — Error Handling, Transaction Integrity & Observability  
**Step**: STEP 3 — BREAK  
**Status**: COMPLETED  

---

## 1. Symptom & Reproduction
The defect was reproduced by simulating a database write failure during link creation:
- Endpoint: `POST /api/v1/links`
- Expected behavior under failure: `HTTP 500 Internal Server Error` with `db.rollback()`.
- Defect behavior observed: Swallowed exception returning `HTTP 201 Created` with dummy `id: 999999`.

---

## 2. Reproduction Evidence
Executing `apps/api/scripts/reproduce_break.py` against the broken endpoint state:

```text
======================================================================
=== REPRODUCING MODULE 05 BREAK SYMPTOM ===
Assigned Difficulty: Easy – Swallowed Exception (Hiding Failure)
Instructor Diagnostic Hint: 'Compare response vs DB state.'
======================================================================

[STEP 1] Client sends POST /api/v1/links with valid API key and payload...
HTTP Status Code: 201 Created
Response Body: {
  "id": 999999,
  "code": "tyEbbJa",
  "short_url": "http://testserver/r/tyEbbJa",
  "long_url": "https://example.com/break-test-destination",
  "created_by": "org_a"
}

[STEP 2] Comparing response vs DB state for code 'tyEbbJa'...
Database Query: db.query(Link).filter(Link.code == 'tyEbbJa').first()
Database Record Found: None

[STEP 3] Client attempts to access generated short link GET /r/tyEbbJa...
Redirect Status Code: 404 Not Found
Redirect Response Body: {"error": {"code": "NOT_FOUND", "message": "Short code not found"}}

[CONFIRMED BREAK SYMPTOM]
1. API returned success status code (HTTP 201 Created) to caller.
2. Internal database transaction failed and was SILENTLY SWALLOWED.
3. Database record check confirmed 0 rows persisted (db_record is None).
4. Public redirect GET /r/tyEbbJa failed with HTTP 404 Not Found.
```

---

## 3. Defect Classification
- **Category**: Swallowed Exception / False-Success Response / Silent Data Loss.
- **Security & Reliability Property Violated**: ACID atomicity, HTTP protocol semantics, and observability transparency.
