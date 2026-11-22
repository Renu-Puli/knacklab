# Module 08 — Decision: Search, Advanced Queries & Optimization Strategy

## 1. Problem Statement
LinkOps tenants need fast, filtered search capabilities (searching URL patterns, filtering by active/expired status, and tag filtering) along with sub-millisecond pagination and efficient analytics aggregations. Currently, list operations rely on single-column indexing, requiring explicit sorting operations, and analytics queries scan separate indices.

## 2. Evaluated Optimization Strategies

### Option A: Database-Level Optimizations (Composite Indexes, Keyspread Pagination & Full-Text/ILIKE Search)
- **Design**:
  1. Add a composite index `ix_links_tenant_created` on `links (created_by, created_at DESC, id DESC)` to satisfy the multi-tenant list/sort order directly without a sort step.
  2. Add a composite index `ix_click_events_link_clicked` on `click_events (link_id, clicked_at DESC)` to optimize date-range analytics aggregations.
  3. Implement keyset / cursor-based pagination alongside offset pagination for high-volume datasets.
  4. Implement database-level keyword filtering (`long_url ILIKE` / tag matching) and active status filters directly in SQLAlchemy queries with tenant isolation enforced.
  5. Provide a batch analytics endpoint or aggregated query to eliminate N+1 query patterns for tenant dashboards.
- **Pros**: Directly leverages PostgreSQL capabilities without introducing external search engine overhead; fully ACID compliant; preserves multi-tenant security.
- **Cons**: Requires schema index updates.

### Option B: External Search Engine (Elasticsearch / OpenSearch)
- **Design**: Sync link metadata and click events to an Elasticsearch cluster.
- **Pros**: Scalable full-text search across billions of links.
- **Cons**: Major infrastructure overhead, data duplication, eventual consistency latency, and unnecessary complexity for current local operational requirements.

## 3. Decision
**Selected Option A (Database-Level Optimization & Advanced Query Patterns)**.
We will implement composite indexing, filtered search with URL and tag matching, keyset pagination support, and batch analytics aggregation to prevent N+1 queries.
