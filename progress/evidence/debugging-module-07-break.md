# Debugging & Incident Response — Module 07: Break

**Track**: `debugging-incident-response`  
**Module**: 07 — Background Jobs & Analytics Decoupling  
**Step**: STEP 3 — BREAK  
**Status**: COMPLETED  

---

## 1. Symptom & Reproduction
The defect was reproduced by executing `scripts/reproduce_module_07_break.py`:
1. Created a short link: `code=AYu73vI, id=1053`.
2. Verified baseline analytics: `total_clicks = 0`.
3. Worker processed a click event with a unique `click_event_id=evt_break_...`.
4. Verified analytics count after first attempt: `total_clicks = 1`.
5. Simulated a Celery task network retry / queue redelivery by re-dispatching the exact same payload with identical `click_event_id`.
6. Defect behavior observed: The worker executed a naive `db.add(ClickEvent(...))` without deduplication, inserting a second row into PostgreSQL.
7. Result: `total_clicks` jumped from 1 to 2 for a single redirect click.

---

## 2. Reproduction Evidence

```text
======================================================================
MODULE 07 BREAK REPRODUCTION: Medium – Job Not Idempotent (Duplicates)
======================================================================

[Step 1] Created short link: code=AYu73vI, id=1053
[Step 2] Baseline analytics: total_clicks = 0

[Step 3] Processing click event (First Attempt): click_event_id=evt_break_c5ab025f8068
  -> Worker response: {'status': 'recorded', 'click_event_id': 'evt_break_c5ab025f8068', 'link_id': 1053, 'id': 2392}
  -> Analytics count after 1 click: total_clicks = 1

[Step 4] Simulating Celery task retry/redelivery with IDENTICAL payload...
  -> Re-dispatching click_event_id=evt_break_c5ab025f8068
  -> Worker response: {'status': 'recorded', 'click_event_id': 'evt_break_c5ab025f8068', 'link_id': 1053, 'id': 2393}

[Step 5] Analytics count after simulated retry: total_clicks = 2
  -> Total click_events rows in DB for link_id 1053: 2

----------------------------------------------------------------------
REPRODUCTION RESULT:
FAILURE CONFIRMED: Job is NOT idempotent!
A single click event was processed twice on retry, resulting in 2 recorded clicks.
Expected behavior: total_clicks should remain 1 because click_event_id was identical.
Observed behavior: duplicate record was inserted, inflating analytics metrics.
----------------------------------------------------------------------
```

---

## 3. Defect Classification
- **Category**: At-Least-Once Delivery Failure / Non-Idempotent Consumer / Metrics Double-Counting.
- **Impact**: Inaccurate analytics reporting, corrupted customer billing, and redundant database storage consumption.
