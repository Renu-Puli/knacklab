# Module 09 — Decision: Partitioning Architecture & Safe Local Demonstration

## 1. Problem Statement
The high-volume `click_events` table requires safe horizontal scalability, fast date-bounded queries, and zero-downtime data retention cleanup without locking the hot path or thrashing shared buffers.

## 2. Evaluated Partitioning Strategies

### Option A: Declarative Time-Range Partitioning on `clicked_at`
- **Architecture**:
  - Partition `click_events_partitioned` by `RANGE (clicked_at)`.
  - Create monthly partitions: `click_events_2026_10`, `click_events_2026_11`, `click_events_2026_12`, and a `click_events_default` partition.
  - Foreign key and query routing automatically handled by PostgreSQL query planner via Partition Pruning.
- **Benefits**:
  - Direct partition pruning on date-bounded queries (e.g., last 30 days only scans 1 or 2 small partition tables).
  - Data retention cleanup becomes a zero-cost $O(1)$ DDL operation (`DROP TABLE` / `DETACH PARTITION`) instead of expensive and bloat-inducing `DELETE` queries.
  - Completely preserves PostgreSQL ACID guarantees and multi-tenant isolation.
- **Drawbacks**: Primary key must include the partition key `clicked_at`.

### Option B: Hash Sharding on Tenant `created_by`
- **Architecture**: Hash partition by tenant organization.
- **Benefits**: Isolates noisy neighbor tenants into separate partitions.
- **Drawbacks**: Does not optimize date-bounded scans or simplify automated retention purges.

## 3. Decision
**Selected Option A (Time-Range Declarative Partitioning with Automated Partition Pruning & Zero-Cost Retention)**.
We will construct a high-performance declarative partitioned architecture for click analytics, verify partition pruning with `EXPLAIN ANALYZE`, prove tenant-isolated query routing, and demonstrate $O(1)$ partition detachment for retention.
