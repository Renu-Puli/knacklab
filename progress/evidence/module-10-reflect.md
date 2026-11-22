# Module 10 — Reflect: Zero-Downtime Database Migrations & Safe Deployment Sequences

## 1. Architectural Lessons & Deployment Sequence

### A. The Inevitability of Mixed-Version Clusters
- In continuous delivery, rolling updates mean that $V_{old}$ and $V_{new}$ instances of an application concurrently process user requests for several minutes.
- Schema changes that assume an instantaneous, atomic cutover will cause outage incidents if they break contract expectations of the older version.

### B. The 5-Phase Expand-and-Contract Pattern
1. **Expand Schema**: Add columns with non-blocking server defaults (`DEFAULT true`) and nullable types. In PostgreSQL 11+, constant defaults update the catalog without table-level write locks.
2. **Dual-Support Code**: Deploy application code that can read and write the new fields while gracefully accepting legacy payloads.
3. **Backfill**: Incrementally backfill historical rows without acquiring long-lived locks.
4. **Contract Constraints**: Apply `NOT NULL` or foreign key constraints using safe PostgreSQL validation stages (`ADD CONSTRAINT ... NOT VALID` followed by `VALIDATE CONSTRAINT`).
5. **Contract Cleanup**: Remove deprecated columns only after all older application versions are decommissioned.

### C. Safe Rollback Strategy
- Because the initial schema expansion is strictly additive, rolling back an application deployment from $V_{new}$ to $V_{old}$ requires zero database downtime and zero emergency schema reverts.
