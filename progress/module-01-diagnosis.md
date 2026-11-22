# Module 01 Diagnosis Notes

## Bug 1 — Database Connection / Startup Failure
- Symptom: Service fails to connect to the database on startup.
- Hypothesis A: The database container (PostgreSQL) is not running or listening on port 5432.
  - Command: `docker ps` and socket check on 127.0.0.1:5432
  - Observation: Verified through `docker ps -a` that `upsk-sdf-postgres` exited 2 hours ago (Exited 255), and socket check on 127.0.0.1:5432 returned False (not listening).
  - Result: Supported.
- Hypothesis B: Database connection parameters (host, port, credentials, database name) in configuration differ from container configuration.
  - Command: Inspected `apps/api/.env`, `apps/api/.env.example`, `apps/api/app/database.py`, and `docker inspect upsk-sdf-postgres` (credentials redacted).
  - Observation:
    - Host: `localhost` in `.env` / `database.py` matches container port mapping `0.0.0.0:5432->5432/tcp`.
    - Port: `5432` in `.env` matches container listening port `5432`.
    - Database Name: `upsk_sdf` in `.env` matches container environment `POSTGRES_DB=upsk_sdf`.
    - User: `postgres` in `.env` matches container environment `POSTGRES_USER=postgres`.
    - Driver normalization in `app/database.py` properly converts `postgres://` to `postgresql+psycopg://`.
  - Result: Rejected (No configuration mismatch identified; the configuration matches the container settings, but the container process itself is stopped).
- Fix: Started the existing PostgreSQL container without recreation or volume removal via `docker start upsk-sdf-postgres`.
- Verification proof:
  - Container status (`docker ps --filter "name=upsk-sdf-postgres"`): Status `Up 24 seconds`, mapped `0.0.0.0:5432->5432/tcp`.
  - Database engine readiness (`docker exec upsk-sdf-postgres pg_isready -U postgres -d upsk_sdf`): Output `/var/run/postgresql:5432 - accepting connections`.
  - Host network socket: TCP connection check to `127.0.0.1:5432` confirmed `Port 5432 listening: True`.
  - Distinction: Container reached `Up` state, engine confirmed `accepting connections`, and host port `5432` is actively listening. Data volumes preserved intact.

## Bug 2 — Pagination Duplicates Across Page Boundaries
- Symptom: The last item on Page 1 appears again as the first item on Page 2 when listing links with pagination.
- Hypothesis 1: The pagination offset calculation is incorrect, causing page boundaries to overlap by one record (off-by-one).
  - Inspection Source: `apps/api/app/routers/links.py`, lines 91–110 (`list_links` endpoint).
  - Parameter Definition: `skip: int = Query(default=0, ge=0, description="Pagination offset")`, `limit: int = Query(default=20, ge=1, le=100, description="Items per page")`.
  - Database Query Construction:
    ```python
    links = (
        db.query(Link)
        .filter(Link.created_by == effective_org)
        .order_by(Link.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    ```
  - Analysis & Mathematical Check:
    - The existing API does not compute `offset` from a `page` formula (e.g., `(page - 1) * limit`); rather, it exposes `skip` directly to callers.
    - If a client or upstream admin wrapper converts `page` to offset using an off-by-one calculation like `offset = (page - 1) * limit - 1` (or if `page=1 -> offset=0` and `page=2 -> offset=9`), records 0..9 and 9..18 overlap at index 9 (record #10).
    - When `offset=0, limit=10` is passed for Page 1 and `offset=10, limit=10` is passed for Page 2, a non-destructive read test on the live database returned Page 1 IDs `[811, ..., 802]` and Page 2 IDs `[801, ..., 792]` with `Overlap P1 & P2: set()` (zero overlap).
    - However, the lab scenario specifies client calls using query parameters `?page=1&limit=10` and `?page=2&limit=10` against admin link listing. Currently, `apps/api/app/routers/links.py` only defines `skip` and does not provide `page` parameter calculation or mapping.
  - Result: Inconclusive / Partially Rejected locally (The backend `skip` and `offset(skip)` mechanism itself does not contain an internal off-by-one subtraction, but the endpoint does not yet support the scenario's requested `?page=` contract).
- Hypothesis 2: The sort order is unstable.
  - Inspection Source: `apps/api/app/routers/links.py`, line 106.
  - Ordering Clause: `.order_by(Link.created_at.desc())`
  - Analysis of Sort Key:
    - The sorting column `Link.created_at` is a non-unique timestamp.
    - No unique secondary tie-breaker (such as `Link.id.desc()` or `Link.code`) is included in the `.order_by()` clause.
    - Read-only database query verified actual rows sharing identical timestamps (e.g., records with ID `687` and `688` share `created_at = 2026-11-20 04:20:41.564779+00:00`).
    - In relational database theory (PostgreSQL SQL standard), sorting by a non-unique attribute without a unique tie-breaker produces nondeterministic tuple sequencing when equal values span an `OFFSET`/`LIMIT` page boundary. If concurrent writes, VACUUM, or plan changes shift physical heap page ordering, records with identical timestamps can swap relative positions, causing an item to appear on both pages or vanish.
    - However, on the current static dataset, sequential read queries with `limit=1, offset=0` and `limit=1, offset=1` returned `[687]` and `[688]` consistently without immediate intra-query swapping.
  - Result: Partially Supported in theory (sorting is mathematically non-deterministic without a tie-breaker, though active live duplication was not reproduced on static sequential reads).
- Fix:
  - Updated `apps/api/app/routers/links.py` in `list_links` to support the official `page` query parameter alongside `limit` (`offset = (page - 1) * limit`).
  - Preserved backward compatibility for callers passing `skip` directly (if `page` is provided, it takes precedence; otherwise `skip` is used).
  - Added deterministic secondary sort tie-breaker `.order_by(Link.created_at.desc(), Link.id.desc())` so rows sharing identical timestamps maintain a strictly deterministic position.
- Verification proof:
  - Curl 3-page verification (`http://localhost:8000/links?page={1,2,3}&limit=10` with `X-API-Key: test-api-key-org-a`):
    - Page 1 IDs (count 10): `[811, 810, 809, 808, 807, 806, 805, 804, 803, 802]` (HTTP 200)
    - Page 2 IDs (count 10): `[801, 800, 799, 798, 797, 796, 795, 794, 793, 792]` (HTTP 200)
    - Page 3 IDs (count 10): `[791, 790, 789, 788, 787, 786, 785, 784, 783, 782]` (HTTP 200)
  - Duplicate / Boundary Analysis:
    - Page 1 last ID (802) != Page 2 first ID (801).
    - Page 2 last ID (792) != Page 3 first ID (791).
    - Overlap P1 & P2: `set()` (Zero overlap).
    - Overlap P2 & P3: `set()` (Zero overlap).
    - Overlap P1 & P3: `set()` (Zero overlap).
  - Backward compatibility check: `GET /links?skip=10&limit=10` returned identical Page 2 IDs `[801, ..., 792]` (HTTP 200).
  - Tenant isolation check: Verified `X-API-Key: test-api-key-org-b` returned only Org B links (2 records), and unauthenticated request returned HTTP 401 Unauthorized.
  - Regression check: Module 05 verification suite passed 9/9 checks.

## Step 6: Fix — Concurrency Simulation & Offset Drift Evaluation
- Verification Script: `scripts/verify_module_01_fix.py`
- Setup: Dedicated test tenant (`concurrent_test_tenant`) with 35 seeded links.
- Test A (Static baseline):
  - Page 1: `[879, ..., 870]`, Page 2: `[869, ..., 860]`, Page 3: `[859, ..., 850]`.
  - Overlap P1/P2: `set()`, Overlap P2/P3: `set()`. Zero duplicates.
- Test B (Concurrent insertions between pages):
  - Step 1: Fetched Page 1 (`offset=0, limit=10`). Boundary item at bottom: ID `870` (and `871` at index 8).
  - Step 2: Inserted 2 new links (`881`, `882`) prepended to dataset (`created_at DESC, id DESC`).
  - Step 3: Fetched Page 2 (`offset=10, limit=10`). Returned IDs: `[871, 870, 869, 868, 867, 866, 865, 864, 863, 862]`.
  - Step 4: Overlap P1 & P2: `{870, 871}`.
- Finding & Architectural Limitation:
  - Deterministic sorting (`created_at DESC, id DESC`) guarantees consistent tuple sequence on static datasets and identical query runs.
  - However, offset-based pagination (`OFFSET N LIMIT M`) is inherently vulnerable to "offset drift" across mutating datasets: inserting $K$ records at the top pushes $K$ records across the offset boundary into the subsequent page.
  - On static reads following the insertion, sequential pages 1, 2, 3 again exhibit zero duplicate overlap:
    - Post-insert Page 1: `[882, 881, 879, 878, 877, 876, 875, 874, 873, 872]`
    - Post-insert Page 2: `[871, 870, 869, 868, 867, 866, 865, 864, 863, 862]`
    - Post-insert Page 3: `[861, 860, 859, 858, 857, 856, 855, 854, 853, 852]`
    - Overlap: `set()` (Zero overlap across all post-insert pages).
