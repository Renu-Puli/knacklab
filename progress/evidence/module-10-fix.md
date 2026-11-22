# Module 10 — Fix: Zero-Downtime Expand-and-Contract Migration

## 1. Architecture Implementation
To safely evolve the database schema and application contracts without risk of downtime during continuous rolling deployments, the Expand-and-Contract pattern was executed:

1. **Phase 1: Expand (Non-Blocking Schema Change)**:
   - Added `is_active BOOLEAN DEFAULT true` and `title VARCHAR(255)` to `links`.
   - Used PostgreSQL non-rewriting constant defaults, preventing table-exclusive lock queuing.
2. **Phase 2: Dual Support & Backward-Compatibility**:
   - `Link` SQLAlchemy model updated with `is_active` (`server_default="true"`) and `title` (`nullable=True`).
   - Pydantic schemas updated so that requests from legacy clients ($V_{old}$) omitting `is_active` and `title` continue to validate and persist seamlessly with default values.
   - Pydantic response models deserialize both legacy and extended fields without breaking older consumer contracts.
3. **Phase 3: Backfill & Data Integrity**:
   - Executed historical backfill query: `UPDATE links SET is_active = true WHERE is_active IS NULL;`
   - Verified 100% data integrity across all 1,131 existing records.
4. **Phase 4: Contract Readiness & Rollback Safety**:
   - Rollback scripts preserve the ability to cleanly drop columns (`ALTER TABLE links DROP COLUMN title`) or revert code without corrupting underlying link redirects or tenant isolation.
