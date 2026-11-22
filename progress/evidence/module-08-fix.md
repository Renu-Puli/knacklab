# Module 08 — Fix: Search, Advanced Queries & Index Optimization

## 1. Overview of Changes
To address query performance bottlenecks, sorting overheads, sequential table scans, and N+1 query patterns, the following changes were implemented:

1. **Composite Indexes**:
   - `ix_links_tenant_created` on `links (created_by, created_at DESC, id DESC)`: Completely satisfies tenant-scoped ordering without requiring an in-memory Sort step in PostgreSQL.
   - `ix_click_events_link_clicked` on `click_events (link_id, clicked_at DESC)`: Speeds up date-bounded click analytics scans.
   - `ix_links_tags` on `links (tags)`: Speeds up tag-based search queries.
2. **Advanced Filtering & Keyset Pagination in `apps/api/app/routers/links.py`**:
   - `query`: Case-insensitive substring matching against `long_url` or short `code` using `ILIKE`.
   - `tag`: Case-insensitive tag matching.
   - `status`: Dynamic filtering for `active` (`expires_at IS NULL OR expires_at > NOW()`) vs `expired`.
   - `cursor_id`: O(1) keyset pagination (`WHERE id < cursor_id ORDER BY created_at DESC, id DESC LIMIT :limit`) avoiding large offset penalties.
3. **N+1 Prevention with Batch Analytics (`GET /links/analytics/batch`)**:
   - Accepts up to 50 comma-separated link IDs.
   - Validates multi-tenant ownership in a single query.
   - Executes a single `GROUP BY link_id` aggregation to fetch total clicks and last click timestamps in one database round-trip.
