# Module 03: Reproduction Science — STEP 3: BUILD

## 1. Candidate Hypotheses & Variable Isolation

| Candidate | Description | Log & Architectural Analysis | Status |
| :--- | :--- | :--- | :--- |
| **Candidate 1: Data** | Certain links have malformed characters, slugs, or metadata causing failures. | Logs show intermittent 500s occur specifically on popular, high-traffic links while low-traffic links with diverse slugs succeed. | **Deprioritized** |
| **Candidate 2: Timing** | Failures coincide with timestamp bucket rollovers (e.g., hourly boundaries). | Intermittent 500s appear randomly throughout the hour, not correlated strictly with bucket transitions. | **Deprioritized** |
| **Candidate 3: Concurrency** | Simultaneous requests for the same popular short link arrive within the same millisecond window, triggering a check-then-act race condition in analytics/click recording. | High correlation with traffic volume per link; popular links receive concurrent bursts, while single-request links succeed consistently. | **Primary Working Hypothesis** |

---

## 2. Reproduction Artifact Built

- **File**: `scripts/repro_race.py` (mirrored in `apps/api/scripts/repro_race.py`)
- **Design Principles**:
  - **Minimal Moving Parts**: Focuses purely on concurrency against a single target key (`CONCURRENCY = 10`).
  - **Synthetic Data Only**: Uses synthetic tenant `synthetic_tenant_repro` and mock destination URLs; zero customer tokens, secrets, or PII.
  - **Dual Transport Flexibility**: Supports both live HTTP loopback (`http://localhost:8000`) and in-process ASGI transport (`httpx.ASGITransport(app=app)`).
  - **Categorized Outcome Accounting**: Aggregates successful redirects (`301`, `302`, `307`), server errors (`500`), client errors (`4xx`), and network exceptions.
- **Verification of Build**:
  - Successfully compiled via `py_compile` with zero syntax errors.
  - No stress run or execution attempts executed yet, preserving the baseline state for authorized experimentation.
