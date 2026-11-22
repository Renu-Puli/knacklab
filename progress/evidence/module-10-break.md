# Module 10 — Break: Unsafe Migration Failures & Application Incompatibility

## 1. Problem Reproduction
To demonstrate why naive migrations cause downtime during continuous deployments, two realistic breaking failure modes were reproduced in `scripts/break_module_10.py`:

### Failure Mode 1: Destructive NOT NULL Addition on Populated Tables
- **Action**:
  ```sql
  ALTER TABLE links_migration_drill ADD COLUMN is_active BOOLEAN NOT NULL;
  ```
- **Result**:
  `(psycopg.errors.NotNullViolation) column "is_active" of relation "links_migration_drill" contains null values`
- **Impact**: The migration halts deployment immediately with a fatal database exception, or in engines requiring table rewrites, locks the entire production table, stalling all incoming redirect and link queries.

### Failure Mode 2: Legacy Version Incompatibility ($V_{old}$ Crash)
- **Action**: A migration sets `NOT NULL DEFAULT true`, but older application pods ($V_{old}$) do not populate or explicitly pass deserialized `null` defaults.
- **Result**:
  `(psycopg.errors.NotNullViolation) null value in column "is_active" of relation "links_migration_drill" violates not-null constraint`
- **Impact**: Uncaught $500$ Internal Server Errors for end users on all legacy pods until the deployment is either rolled back or completes across 100% of the fleet.
