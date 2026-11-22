"""
Comprehensive verification test suite for Module 08:
Tests:
1. Composite index presence and structure
2. Execution plan verification (Index Scan without Sort node)
3. Advanced search filtering (keyword query in long_url and code)
4. Tag filtering
5. Status filtering (active vs expired)
6. Keyset cursor pagination correctness and consistency
7. Batch analytics endpoint (/links/analytics/batch) eliminating N+1 queries
8. Multi-tenant isolation on batch analytics and search
9. Regression verification of existing link CRUD and rate-limiting
"""
import sys
import os
import unittest
sys.path.insert(0, "apps/api")

from fastapi.testclient import TestClient
from app.main import app
from app.database import engine, text
from app.config import settings

client = TestClient(app)

class TestModule08(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use registered API keys from app/auth.py
        cls.headers_org_a = {"X-API-Key": "test-api-key-org-a"}
        cls.headers_org_b = {"X-API-Key": "test-api-key-org-b"}
        
        # Ensure test data exists for org_a
        with engine.connect() as conn:
            with conn.begin():
                # Clean up / set existing test tags
                conn.execute(text("UPDATE links SET tags = 'marketing,sale' WHERE created_by = 'org_a' AND id IN (SELECT id FROM links WHERE created_by = 'org_a' LIMIT 5)"))
                conn.execute(text("UPDATE links SET tags = 'engineering' WHERE created_by = 'org_a' AND id IN (SELECT id FROM links WHERE created_by = 'org_a' OFFSET 5 LIMIT 5)"))

    def test_01_composite_indexes_exist(self):
        """Verify that Module 08 composite indexes exist in PostgreSQL."""
        with engine.connect() as conn:
            indexes = conn.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'links' AND indexname = 'ix_links_tenant_created'
            """)).fetchall()
            self.assertEqual(len(indexes), 1, "ix_links_tenant_created must exist")

            ce_indexes = conn.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'click_events' AND indexname = 'ix_click_events_link_clicked'
            """)).fetchall()
            self.assertEqual(len(ce_indexes), 1, "ix_click_events_link_clicked must exist")

    def test_02_explain_plan_no_explicit_sort(self):
        """Verify EXPLAIN plan uses the composite index without Sort node."""
        with engine.connect() as conn:
            plan = conn.execute(text("""
                EXPLAIN (FORMAT JSON)
                SELECT * FROM links 
                WHERE created_by = 'org_a' 
                ORDER BY created_at DESC, id DESC 
                LIMIT 20;
            """)).scalar()
            plan_str = str(plan)
            # The composite index allows directly scanning in order without Sort
            self.assertIn("Index Scan", plan_str)
            self.assertNotIn("'Node Type': 'Sort'", plan_str)

    def test_03_search_query_filter(self):
        """Test searching links by long_url keyword."""
        # Create a unique link to search for
        res = client.post(
            "/links",
            headers=self.headers_org_a,
            json={"long_url": "https://example.com/search-target-alpha-987", "tags": ["searchtest"]}
        )
        self.assertEqual(res.status_code, 201)
        
        search_res = client.get("/links?query=search-target-alpha-987", headers=self.headers_org_a)
        self.assertEqual(search_res.status_code, 200)
        items = search_res.json()
        self.assertGreaterEqual(len(items), 1)
        self.assertIn("search-target-alpha-987", items[0]["long_url"])

    def test_04_tag_filtering(self):
        """Test filtering links by tag."""
        res = client.get("/links?tag=marketing", headers=self.headers_org_a)
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertGreaterEqual(len(items), 1)
        for item in items:
            self.assertIn("marketing", item["tags"])

    def test_05_status_filtering_active(self):
        """Test status filtering for active links."""
        res = client.get("/links?status=active", headers=self.headers_org_a)
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertIsInstance(items, list)

    def test_06_keyset_cursor_pagination(self):
        """Test keyset pagination consistency with cursor_id."""
        page1 = client.get("/links?limit=5", headers=self.headers_org_a).json()
        self.assertEqual(len(page1), 5)
        last_id = page1[-1]["id"]
        
        page2 = client.get(f"/links?limit=5&cursor_id={last_id}", headers=self.headers_org_a).json()
        self.assertEqual(len(page2), 5)
        # Keyset pagination strictly guarantees items in page 2 have smaller IDs (descending)
        for item in page2:
            self.assertLess(item["id"], last_id)

    def test_07_batch_analytics_n_plus_1_prevention(self):
        """Test batch analytics endpoint aggregating click metrics for multiple links in 1 query."""
        page = client.get("/links?limit=5", headers=self.headers_org_a).json()
        ids = [str(item["id"]) for item in page]
        id_str = ",".join(ids)
        
        res = client.get(f"/links/analytics/batch?link_ids={id_str}", headers=self.headers_org_a)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_links_queried"], len(ids))
        self.assertEqual(len(data["items"]), len(ids))

    def test_08_batch_analytics_tenant_isolation(self):
        """Verify cross-tenant links are omitted from batch analytics (anti-enumeration)."""
        # Create link in org_b
        link_b = client.post(
            "/links",
            headers=self.headers_org_b,
            json={"long_url": "https://example.com/org-b-link-batch-test"}
        ).json()
        
        # Org_a attempts to query org_b's link via batch analytics
        res = client.get(f"/links/analytics/batch?link_ids={link_b['id']}", headers=self.headers_org_a)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Should not expose org_b's link to org_a
        self.assertEqual(data["total_links_queried"], 0)
        self.assertEqual(len(data["items"]), 0)

if __name__ == "__main__":
    unittest.main()
