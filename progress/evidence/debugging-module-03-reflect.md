# Module 03: Reproduction Science — STEP 7: REFLECT

## 1. Executive Summary & Narrative
Module 03 addressed the engineering discipline of **Reproduction Science**: transforming ambiguous, intermittent production bug reports into deterministic, scriptable, and automated reproductions. 

The investigation examined a reported production defect where popular short links intermittently returned HTTP 500 errors. Using hypothesis-driven isolation and an asynchronous synthetic reproduction harness, we subjected the system to concurrent load under degraded infrastructure conditions (offline Redis). While the originally reported HTTP 500 was not triggered, the stress experiment revealed and deterministically reproduced a severe architectural defect: **SQLAlchemy `QueuePool` connection starvation** under concurrency. 

A minimal fix decoupled database connection lifecycles from external network I/O, achieving 100% redirect success under stress.

---

## 2. Decision Callback (Closing the DECIDE Loop)

### A. The Decision
In STEP 2 (DECIDE), we evaluated two reproduction approaches:
- **Option A (`production_replay`)**: Capturing live production traffic with tools like GoReplay and replaying captured packets against staging.
- **Option B (`synthetic_repro`)**: Writing a minimal, targeted asynchronous script simulating concurrent requests against specific resources.

We selected **Option B (`synthetic_repro`)** (`decisions.module_03.repro_approach = synthetic_repro`).

### B. Technical Tradeoff Evaluation
- **Why Synthetic Repro Was Chosen**:
  1. *Variable Isolation*: It allowed direct, fine-grained control over the suspected causal variable—concurrency against a single key (`CONCURRENCY = 10, 25`)—without sifting through disparate traffic streams.
  2. *Privacy & Zero Compliance Risk*: It eliminated the risk of storing and replaying customer tokens, Authorization headers, cookies, and PII.
  3. *Tight Iteration Loop*: A targeted, 20-line asynchronous script was implemented and modified in minutes without deploying heavy packet capture infrastructure.
- **Empirical Consequence of the Decision**:
  - The synthetic harness (`scripts/repro_race.py`) applied simultaneous load directly to a single short code (`test-link`).
  - When scaled to concurrency 25 while Redis was offline, the harness directly triggered and exposed a latent capacity limit: holding database connections while awaiting slow external network I/O exhausted the 15-connection pool.
  - The decision to build a synthetic concurrency test succeeded in surfacing a critical architectural defect that standard functional tests and low-rate production logs completely missed.

---

## 3. What Was Reproduced vs. What Remains Unresolved

### A. What Was Empirically Reproduced
- **SQLAlchemy QueuePool Exhaustion**:
  - Pool capacity: `pool_size=5`, `max_overflow=10`, total capacity = 15 connections.
  - Queue timeout: 30.0 seconds.
  - When concurrency reached 25 with Redis offline, 15 connections were checked out and held while awaiting Redis TCP socket timeouts (~2.0s per attempt).
  - The remaining 10 queued requests waited 30.0 seconds and failed with `sqlalchemy.exc.TimeoutError`.
  - Baseline testing at concurrency 10 completed with 10/10 successes, proving that concurrency relative to pool capacity (15) was the exact failure threshold.

### B. What Remains Unresolved
- **The Original Intermittent HTTP 500**:
  - The originally reported intermittent HTTP 500 on popular links was **NOT reproduced** in either baseline (10) or stress (25) tests with Redis offline.
  - The application caught Redis connection failures gracefully (`"Redis initialization failed ... Cache will run in fallback mode"` / `"Failed to enqueue click event ... Error 10061"`), logged warnings, and returned HTTP 307 redirects via PostgreSQL fallback.
  - The intermittent 500 error likely requires active Redis operations (e.g., race conditions during concurrent cache population, cache-aside stampedes, or Celery task serialization conflicts) rather than offline fallback.
- **Redis-Offline Latency**:
  - When Redis is stopped, requests incur significant latency (~51s–117s) due to cascading socket timeouts. Database connections are no longer starved, but client-facing latency remains degraded when background infrastructure is down.

---

## 4. Verification & Timing Discrepancy Analysis

### A. Verification Outcome
- **Test V1 (Concurrency 10)**: 10/10 HTTP 307 (100% success), 0 exceptions, 0 QueuePool timeouts.
- **Test V2 (Concurrency 25)**: 25/25 HTTP 307 (100% success), 0 exceptions, 0 QueuePool timeouts.
- **QueuePool Exhaustion**: Fully resolved.

### B. Timing Discrepancy in Test V2
- **Observed Metrics**:
  - Total batch duration (from first log line at `12:53:00.32` to last log line at `12:54:51.46`): **~111.1 seconds**.
  - Final reported per-request latency in server logs: **`117,300.69ms` (~117.3 seconds)**.
- **Status of Explanation**:
  - *Unverified Hypothesis*: The difference between monotonic `time.perf_counter()` inside FastAPI's request middleware (which measures from request inception) and wall-clock timestamps (`datetime.now(timezone.utc)`) in serialized JSON logs across 25 concurrent ASGI coroutines on a single Python event loop may account for the timing skew.
  - *Explicit Disclosure*: This event-loop / log-serialization explanation is an **unverified hypothesis**, not an empirically proven fact. The timing discrepancy is explicitly documented as an observed anomaly.

---

## 5. Lessons Learned & Production Principles

1. **Connection Checkout Scoping**: Database connections are expensive, finite resources. They must be acquired as late as possible, held for the minimum duration required for the query, and released immediately before initiating external network I/O.
2. **Intellectual Honesty in Incident Response**: When a reproduction experiment triggers a failure different from the reported defect, engineers must report exactly what failed. Fixing a real, verified vulnerability (`QueuePool` exhaustion) while explicitly acknowledging that the original symptom (HTTP 500) remains unconfirmed is the hallmark of rigorous engineering.
3. **Synthetic Harnesses as Regression Tests**: A minimal reproduction script written during an incident should transition directly into an automated CI stress/regression test to guard against future connection leakage.
