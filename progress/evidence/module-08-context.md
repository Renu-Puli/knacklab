# Module 08 — Context: Search, Advanced Queries & Database Performance

## 1. Executive Summary
This document analyzes the query patterns, database schema, indexing strategies, and performance characteristics of the LinkOps multi-tenant URL shortener as part of Module 08.

## 2. Existing Schema & Query Inspection
The current data model consists of two primary operational tables:
- `links`:
  - `id` (PK, indexed)
  - `code` (unique, indexed)
  - `long_url` (text, unindexed)
  - `created_at` (timestamp with time zone, unindexed)
  - `created_by` (tenant ID string, indexed via `ix_links_created_by`)
  - `expires_at` (timestamp with time zone, unindexed)
  - `tags` (comma-separated string, unindexed)
- `click_events`:
  - `id` (PK, indexed)
  - `click_event_id` (unique, indexed)
  - `link_id` (FK to links.id, indexed via `ix_click_events_link_id`)
  - `clicked_at` (timestamp with time zone, indexed via `ix_click_events_clicked_at`)
  - `user_agent`, `referrer`, `ip_hash` (unindexed)

## 3. Query Bottlenecks & Architectural Inefficiencies Identified
1. **Inefficient Multi-Tenant Pagination & Sort (`list_links`)**:
   - Query: `SELECT * FROM links WHERE created_by = :org ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset`
   - Problem: While `created_by` is indexed alone, PostgreSQL must fetch all matching rows for the tenant and perform an in-memory or disk `Sort` on `created_at DESC, id DESC`. Under large tenant datasets and high offsets (`OFFSET 10000`), offset pagination incurs high page-fetch penalties.
   - Missing Index: No composite index on `(created_by, created_at DESC, id DESC)` exists.
2. **Missing Search & Filtering Capabilities**:
   - Tenants currently cannot search links by URL keywords, filter by active/expired status, or filter by specific tags without retrieving the full list into memory.
   - Sequential scans over `long_url` and `tags` cause CPU spikes as link volume grows.
3. **Analytics Aggregation Overhead & Lack of Composite Index (`get_link_analytics`)**:
   - Query: `SELECT count(id), max(clicked_at) FROM click_events WHERE link_id = :link_id AND clicked_at >= :start AND clicked_at <= :end`
   - Problem: The database has individual indexes on `link_id` and `clicked_at`, forcing a `BitmapAnd` or index scan on `link_id` followed by sequential filtering on `clicked_at`.
   - Missing Index: A composite index on `(link_id, clicked_at)` would allow an Index Only Scan or single-index range scan.
4. **N+1 Potential in Multi-Link Analytics / Summary Dashboards**:
   - When a tenant dashboard requests click counts across multiple links, individual queries per link (`N+1`) saturate connection pools and multiply latency.
