# Module 10 — Decision: Expand-and-Contract Migration Architecture

## 1. Objective
Design and implement an automated Expand-and-Contract migration for LinkOps that adds a new operational column `is_active BOOLEAN` and a metadata column `title VARCHAR(255)` to the `links` table with zero downtime, guaranteed backward-compatibility with older application code, non-blocking default constraints, and a validated rollback path.

## 2. Evaluated Migration Patterns

### Option A: Direct Single-Step Migration (Destructive / Downtime-Prone)
- `ALTER TABLE links ADD COLUMN is_active BOOLEAN NOT NULL;`
- **Flaws**:
  1. Fails immediately on existing rows if no default is provided.
  2. If an older application instance inserts a row without `is_active`, PostgreSQL throws `NotNullViolation` ($500$ error for users).
  3. If rolled back prematurely, application instances expecting the column fail immediately.

### Option B: Five-Stage Expand-and-Contract Pattern (Zero-Downtime Industry Standard)
- **Phase 1: Expand (Schema Change)**
  Add columns with database-level server defaults and nullable constraints:
  ```sql
  ALTER TABLE links ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
  ALTER TABLE links ADD COLUMN IF NOT EXISTS title VARCHAR(255);
  ```
- **Phase 2: Dual Support (Application Compatibility)**
  Application models and schemas support both legacy callers (omitting `is_active`/`title`) and new callers, guaranteeing $V_{old}$ and $V_{new}$ operate concurrently without errors.
- **Phase 3: Backfill (Data Integrity)**
  Backfill existing historical rows (`UPDATE links SET is_active = true WHERE is_active IS NULL;`).
- **Phase 4: Contract (Add Constraints Safely)**
  Enforce `NOT NULL` constraint using safe PostgreSQL syntax without full table rewrites.
- **Phase 5: Rollback & Recovery Validation**
  Validate that rolling back application versions or dropping added columns does not cause data corruption or break legacy services.

## 3. Decision
**Selected Option B (Expand-and-Contract Zero-Downtime Migration Pattern)**.
We will reproduce the breaking failure of an unsafe migration, implement the safe Expand-and-Contract migration, and verify dual compatibility, data integrity, and rollback resilience.
