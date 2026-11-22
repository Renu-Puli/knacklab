# Module 09 — Context: Database Scaling, Partitioning & Sharding

## 1. Executive Summary
This document investigates database scaling, data distribution patterns, and partitioning strategies for high-volume analytics in the LinkOps multi-tenant URL shortener.

## 2. Workload & Growth Characteristics
- In a production URL shortener, the `links` table grows at a modest rate ($O(10^5)$ to $O(10^7)$ records per year), whereas the `click_events` telemetry table grows exponentially ($O(10^7)$ to $O(10^9)$ events).
- As `click_events` grows into tens of gigabytes:
  1. The single table index size exceeds PostgreSQL `shared_buffers`, causing buffer eviction and IO thrashing.
  2. Multi-tenant analytical queries and data retention purges (`DELETE FROM click_events WHERE clicked_at < NOW() - 30 days`) cause massive vacuum overhead, write amplification, and exclusive table lock contention.
  3. Uneven tenant activity (noisy neighbors) can degrade performance across all tenants.

## 3. Scaling Approaches Evaluated
1. **Vertical Scaling (Scale-Up)**:
   - Upgrading CPU, RAM, and SSD IOPS. Effective up to a certain financial and hardware limit, but does not solve vacuum overhead, retention purging bottlenecks, or table lock contention.
2. **PostgreSQL Declarative Table Partitioning (Scale-Out locally)**:
   - Range partitioning on `clicked_at` (e.g., monthly partitions) or Hash partitioning on `link_id` / tenant key.
   - Allows partition pruning: queries with date ranges only scan the relevant partition tables, reducing scanned pages by orders of magnitude.
   - Allows instant $O(1)$ retention management via `DROP TABLE partition_old` or `ALTER TABLE DETACH PARTITION`, completely eliminating vacuum bloat and row-by-row deletes.
3. **Application-Level Sharding / Horizontal Sharding**:
   - Routing tenant databases across different database nodes based on `org_id` hash.
   - Ideal for multi-region or hyper-scale deployments, but adds distributed transaction complexity, cross-shard join limitations, and operational overhead.
