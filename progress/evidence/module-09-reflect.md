# Module 09 — Reflect: Architectural Tradeoffs, Partitioning & Scaling

## 1. Architectural Lessons & Tradeoffs

### A. Range Partitioning vs. Monolithic Tables
- **Benefit**: Partition pruning drastically cuts down memory footprint and disk I/O. Data retention is transformed from an expensive, lock-inducing $O(N)$ row-by-row deletion process into an instantaneous $O(1)$ DDL operation (`ALTER TABLE DETACH PARTITION` + `DROP TABLE`).
- **Tradeoff**: PostgreSQL requires the partitioning column (`clicked_at`) to be part of the table's composite primary key (`PRIMARY KEY (id, clicked_at)`). Global unique constraints across partitions cannot be enforced on non-partition keys alone without custom extensions or triggers.

### B. Sharding vs. Partitioning
- **Partitioning**: Implemented within a single PostgreSQL instance. It provides significant vertical headroom (handling hundreds of millions of events) while maintaining ACID transactions, single-connection pooling, and zero application-layer routing overhead.
- **Application Sharding**: Distributes data across independent physical database clusters based on tenant key (`org_id`). While sharding provides horizontal scalability beyond a single node, it introduces cross-shard join limitations, two-phase commits, and operational complexity.
- **Verdict**: For LinkOps's architecture, table-level range partitioning on click telemetry combined with single-tenant composite indexing on the primary database offers the optimal balance of throughput, maintainability, and operational simplicity.
