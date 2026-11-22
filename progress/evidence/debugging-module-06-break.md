# Debugging & Incident Response — Module 06: Break

**Track**: `debugging-incident-response`  
**Module**: 06 — Caching With Redis & Cache Invalidation Integrity  
**Step**: STEP 3 — BREAK  
**Status**: COMPLETED  

---

## 1. Symptom & Reproduction
The defect was reproduced by executing `apps/api/scripts/reproduce_module_06_break.py`:
1. Create a short link with an initial destination URL (`https://example.com/initial-v1-destination`).
2. Trigger `GET /r/{code}` to warm the Redis cache.
3. Confirm Redis cache key `link:{code}` holds the initial URL.
4. Send `PATCH /links/{id}` with a new destination URL (`https://example.com/updated-v2-destination-2026`).
5. Query PostgreSQL directly: confirmed PostgreSQL updated to the new URL.
6. Query Redis directly: Redis still held the stale initial URL.
7. Send `GET /r/{code}`: API returned `HTTP 307` redirecting to the **stale old URL** instead of the updated destination.

---

## 2. Reproduction Evidence

```text
======================================================================
MODULE 06 BREAK REPRODUCTION: Cache Not Invalidated on Update
======================================================================

[Step 1] Created short link:
  Link ID:     1052
  Short Code:  NYxi00U
  Initial URL: https://example.com/initial-v1-destination

[Step 2] Warmed cache via GET /r/NYxi00U:
  Status:   307 Temporary Redirect
  Location: https://example.com/initial-v1-destination

[Step 3] Verified Redis cache entry (link:NYxi00U):
  Cached Long URL: https://example.com/initial-v1-destination
  Cached Org ID:   org_a

[Step 4] Submitted PATCH /links/1052:
  Status:       200 OK
  Payload sent: https://example.com/updated-v2-destination-2026
  Returned URL: https://example.com/updated-v2-destination-2026

[Step 5] Direct PostgreSQL query:
  PostgreSQL long_url: https://example.com/updated-v2-destination-2026
  -> PostgreSQL successfully committed the new URL.

[Step 6] Direct Redis cache inspection after update:
  Redis cached long_url: https://example.com/initial-v1-destination
  -> DEFECT CONFIRMED: Redis still holds the STALE old destination!

[Step 7] Client follows public redirect GET /r/NYxi00U:
  HTTP Status:   307 Temporary Redirect
  Redirected to: https://example.com/initial-v1-destination
  -> CRITICAL CONSISTENCY BUG: User redirected to stale old destination!
```

---

## 3. Defect Classification
- **Category**: Cache Invalidation Failure / Cache-Database Inconsistency / Stale Read Anomaly.
- **Impact**: Incorrect destination routing, broken marketing redirects, and loss of data integrity.
