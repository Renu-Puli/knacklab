# Module 08 — Reflect: Tradeoffs, Limitations & Lessons Learned

## 1. Architectural Tradeoffs

### A. Composite Indexing vs. Write Amplification
- **Tradeoff**: Adding the composite index `ix_links_tenant_created (created_by, created_at DESC, id DESC)` reduced list query planning and execution time by 8.6x and eliminated in-memory sorting.
- **Cost**: Every `INSERT` into `links` now updates an additional B-tree index, increasing WAL write volume and storage footprint slightly. For read-heavy URL shortener workloads (read:write ratio typically exceeding 50:1), this tradeoff provides overwhelming net latency benefits.

### B. Keyset (Cursor) vs. Offset Pagination
- **Offset Pagination**: Intuitive for clients requesting arbitrary page numbers (`page=10`), but degenerates at scale ($O(N)$ row traversal where PostgreSQL must scan and discard $N$ rows).
- **Keyset Pagination**: Constant $O(1)$ index seek performance (`WHERE id < cursor_id LIMIT limit`), ensuring performance never degrades even at page 10,000. However, it cannot jump directly to page $N$ without prior cursor state.
- **Resolution**: Both strategies are supported simultaneously in LinkOps.

### C. N+1 Elimination via Batch Endpoints
- Combining multiple entity metric lookups into a single `GROUP BY` query reduced round-trip connection overhead from 290.45 ms down to 19.00 ms (15.2x speedup).
- Strict multi-tenant filtering (`created_by == effective_org`) within the batch query prevents tenant enumeration vulnerabilities.

## 2. Limitations
- Substring `ILIKE '%term%'` on `long_url` currently executes a partial index scan or sequence filter if trigram GIN indexes (`pg_trgm`) are not enabled. For massive multi-million link datasets, enabling `pg_trgm` extension on PostgreSQL is recommended.
