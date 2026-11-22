# Module 01 — STEP 4: VERIFY Evidence & Reflection

## Track: Debugging & Incident Response (`debugging-incident-response`)
## Module: 01
## Step: VERIFY

---

### Bug #1 — Database Connection / Startup Failure

1. **What were your two hypotheses? Which one was right? How did you rule out the other?**
   - **Hypothesis A**: The PostgreSQL container was stopped, causing connection attempts to fail on port 5432.
   - **Hypothesis B**: Database configuration mismatch (incorrect `DATABASE_URL`, host, port, db name, or credentials).
   - **Outcome**: Hypothesis A was correct (`upsk-sdf-postgres` container had exited). Hypothesis B was ruled out by inspecting `apps/api/.env`, `apps/api/.env.example`, `app/database.py`, and container configuration via `docker inspect`. Because credentials, database name (`upsk_sdf`), and port bindings (`5432`) were aligned, the existing container was started directly without modifying configuration or rebuilding infrastructure.

2. **Was the error message helpful or misleading? How do you handle error messages now?**
   - The error message `"Cannot connect to database"` was accurate regarding the immediate symptom, but gave no indication whether the failure was operational (stopped container) or configuration-based.
   - Error messages are now treated as starting points for investigation rather than definitive diagnoses. Verification steps check service state, network connectivity, configuration alignment, and logs before changing code.

3. **How much time was saved by hypothesis-based debugging?**
   - Without exact stopwatch records, numerical claims are avoided. However, systematically testing hypotheses prevented time-consuming actions such as reinstalling PostgreSQL, blindly altering environment variables, recreating containers, or resetting database migrations. Narrowing the investigation to testable causes enabled a fast and targeted resolution.

---

### Bug #2 — Pagination Duplicates Across Boundaries

1. **Which hypothesis led to the fix? Did you test Hypothesis 1 or 2 first?**
   - Hypothesis 1 (incorrect offset calculation) was investigated first. The existing router accepted a direct `skip` parameter rather than the scenario's required `page`-based pagination interface.
   - Hypothesis 2 (unstable sorting) was investigated next. Queries sorted solely by `Link.created_at.desc()`. Database inspection confirmed multiple records shared identical microsecond timestamps, meaning a deterministic tie-breaker was required.
   - The fix addressed both aspects: implemented `offset = (page - 1) * limit` for `page`-based calls while preserving `skip` backward compatibility, and added `Link.id.desc()` as a secondary sort key to ensure deterministic ordering.

2. **Could you have found the issue by just reading the pagination code?**
   - Code inspection identified structural characteristics, but runtime verification across sequential page queries was essential to observe actual boundary behavior.
   - Comparing IDs across Page 1, Page 2, and Page 3 confirmed the absence of overlapping items, demonstrating the necessity of empirical runtime verification over passive code inspection.

3. **What made your hypotheses testable?**
   - The hypotheses were specific and measurable rather than vague assumptions.
   - They were evaluated using sequential pagination queries with `limit=10` at offsets `0`, `10`, and `20`, allowing objective validation that every item appeared on exactly one page and no items were duplicated across boundaries.
