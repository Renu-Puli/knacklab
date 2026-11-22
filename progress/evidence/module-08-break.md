# Module 08 — Break: Query Performance Bottlenecks & N+1 Reproduction

## 1. Executive Summary
This document provides empirical evidence of the unoptimized database query patterns and architectural bottlenecks reproduced in Module 08:
1. **Explicit Sort Overhead in Tenant Pagination**: High offset queries require an explicit sort node (`Sort Method: quicksort` or top-N sort) across candidate tenant rows because no composite index exists on `(created_by, created_at DESC, id DESC)`.
2. **N+1 Query Bottleneck**: When calculating click counts across 20 links for a tenant, executing individual queries per link takes **290.45 ms** across 20 round-trips compared to **37.89 ms** for a single batch `GROUP BY` query (a 7.67x latency penalty).

## 2. Empirical Benchmark Evidence

### Test Case 1: EXPLAIN ANALYZE for Tenant Offset Pagination
- Query:
  ```sql
  EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
  SELECT * FROM links 
  WHERE created_by = 'org_a' 
  ORDER BY created_at DESC, id DESC 
  LIMIT 20 OFFSET 500;
  ```
- **Plan Summary**: `Limit (cost=79.94..79.99)`
- **Node Type**: `Limit` $\rightarrow$ `Sort` (explicit sort required)
- **Total Cost**: 79.99
- **Actual Total Time**: 62.52 ms
- **Root Cause**: Index scan on single-column index `ix_links_created_by` requires fetching rows, followed by an in-memory Sort node to order by `created_at DESC, id DESC`.

### Test Case 2: N+1 Multi-Link Metric Retrieval
- Workload: Fetch total click counts for 20 links belonging to `org_a`.
- **N+1 Pattern (20 round-trips)**: `290.452 ms`
- **Batch Pattern (1 query, GROUP BY)**: `37.889 ms`
- **Measured Penalty**: 7.67x slower; consumes 20 separate database connections/transactions from the pool sequentially.
