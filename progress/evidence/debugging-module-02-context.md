# Module 02 — STEP 1: CONTEXT Evidence

**Track:** Debugging & Incident Response  
**Module:** 02 — Reading Logs Like a Story  
**Step:** 1 — CONTEXT  

---

## Micro-Exercise Analysis & Log Timeline Reconstruction

### 1. Failed Request Analysis
- **Failing Request:** `r-003` (`GET /r/nope99`)
- **Evidence:** Log entry at `2025-01-15T14:00:05.510Z` with level `"error"`, message `"link not found"`, HTTP status `404`, and execution duration `10ms`.
- **Finding:** The request failed because the requested short link code `nope99` does not exist in the database.

### 2. Performance / Latency Analysis
- **Slowest Request:** `r-004` (`POST /links`)
- **Total Latency:** `700ms` (`duration_ms: 700`), completing with HTTP `201 Created` at `14:00:08.900Z`.
- **Bottleneck Identified:** The preceding log entry at `14:00:08.890Z` logged a `"slow db write"` warning taking `680ms` (`duration_ms: 680`) for link `pL3nR`.
- **Potential Root Causes:** Database connection contention, lock wait times, disk I/O saturation, or network latency to the database instance. The logs pinpoint the write operation as the bottleneck, while the request itself still succeeded.

### 3. Failure Pattern Assessment
- **Pattern vs One-off:** Isolated one-off failure and one isolated performance anomaly.
- **Evidence:** 
  - `r-001` (POST /links): 45ms, 201 Created (Success)
  - `r-002` (GET /r/xK9mQ): 12ms, 302 Redirect (Success)
  - `r-003` (GET /r/nope99): 10ms, 404 Not Found (Client/routing error)
  - `r-004` (POST /links): 700ms, 201 Created (Performance anomaly / slow DB write, but completed successfully)
- **Conclusion:** There is no systemic cascade, outage, or widespread failure pattern in this sample.
