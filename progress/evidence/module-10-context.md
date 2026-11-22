# Module 10 — Context: Zero-Downtime Database Migrations & Backward Compatibility

## 1. Executive Summary
This document analyzes zero-downtime database migration methodologies, rolling deployment constraints, and backward-compatible schema evolution for the LinkOps URL shortener.

## 2. The Zero-Downtime Problem in Production
In modern continuous deployment environments:
- Database migrations run **before or concurrently with** application deployment across a multi-instance rolling update cluster (e.g., Kubernetes, ECS, or multi-server blue/green deployments).
- During the deployment window:
  1. Older application pods ($V_{old}$) and newer application pods ($V_{new}$) run simultaneously against the same live database.
  2. If a migration destructively alters, drops, or renames a column (or adds a NOT NULL column without a default value), $V_{old}$ pods will instantly crash with runtime SQL errors (e.g. `psycopg.errors.UndefinedColumn` or `NotNullViolation`).
  3. Rolling back an unsafe migration often requires full system downtime and manual data recovery.

## 3. Real-World Case Study in LinkOps
Suppose LinkOps decides to introduce a structured URL title and metadata feature, transitioning from the raw text field `long_url` to a structured JSONB or normalized destination URL column with custom slug support and an active boolean status column (`is_active` boolean defaulting to `true`).
- **Naive / Destructive Migration**:
  `ALTER TABLE links ADD COLUMN is_active BOOLEAN NOT NULL;` (fails if existing rows exist without default, or crashes older app versions not supplying `is_active`).
- **Expand-and-Contract (Parallel Run) Pattern**:
  1. **Phase 1 (Expand - Schema)**: Add new column as nullable or with a non-locking database server default (`DEFAULT true`).
  2. **Phase 2 (Expand - Code)**: Update application code to read from new or fallback columns and dual-write if necessary. Old application instances continue functioning safely because the column addition is backward-compatible.
  3. **Phase 3 (Backfill)**: Backfill historical rows in small batches without acquiring exclusive table locks.
  4. **Phase 4 (Contract - Enforce)**: Add constraints (`NOT NULL`, foreign keys) using `NOT VALID` followed by `VALIDATE CONSTRAINT` to avoid long table locks.
  5. **Phase 5 (Contract - Cleanup)**: Remove deprecated columns only after 100% of running application pods are updated to $V_{new}$.
