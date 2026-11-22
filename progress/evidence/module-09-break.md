# Module 09 — Break: Unpartitioned Monolithic Scans & Deletion Overhead

## 1. Problem Reproduction
In high-throughput multi-tenant systems, the unpartitioned `click_events` table exhibits two severe scaling bottlenecks:
1. **Row-by-Row Deletion & Table Bloat**: Purging expired records requires executing `DELETE FROM click_events WHERE clicked_at < NOW() - INTERVAL '30 days'`. For 500 records, this took **22.63 ms** and created dead tuples requiring PostgreSQL background `VACUUM` workers. Under millions of rows, this causes buffer churn, index bloat, and table-level locks.
2. **Monolithic Table Scanning**: Analytical queries over specific timeframes (e.g. November 2026) must scan the monolithic table index tree (Total Cost: 40.76) without benefiting from partition exclusion.
