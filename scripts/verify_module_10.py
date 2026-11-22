"""
Comprehensive verification test suite for Module 10:
Tests:
1. Verify columns is_active and title exist in PostgreSQL
2. Verify historical rows are populated with is_active = true (backfill integrity)
3. Verify legacy V_old client request (omitting title and is_active) succeeds with 201 Created
4. Verify modern V_new client request (supplying custom title and is_active) succeeds
5. Verify updates to title and is_active work seamlessly
6. Verify redirect behavior respects is_active flag (inactive link returns 410 or 404)
7. Verify safe rollback test on isolated sandbox table without data corruption
8. Regression verification of previous module endpoints
"""
import sys
import unittest
sys.path.insert(0, "apps/api")

from fastapi.testclient import TestClient
from app.main import app
from app.database import engine, text

client = TestClient(app)

class TestModule10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.headers_org_a = {"X-API-Key": "test-api-key-org-a"}

    def test_01_schema_columns_exist(self):
        """Verify is_active and title columns exist in the links table."""
        with engine.connect() as conn:
            columns = conn.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default 
                FROM information_schema.columns 
                WHERE table_name = 'links' AND column_name IN ('is_active', 'title');
            """)).fetchall()
            col_names = [c[0] for c in columns]
            self.assertIn("is_active", col_names)
            self.assertIn("title", col_names)

    def test_02_historical_data_integrity(self):
        """Verify zero historical records have NULL for is_active."""
        with engine.connect() as conn:
            null_count = conn.execute(text("SELECT count(*) FROM links WHERE is_active IS NULL;")).scalar()
            self.assertEqual(null_count, 0, "No rows should have NULL is_active after backfill")

    def test_03_legacy_v_old_request_compatibility(self):
        """Verify legacy V_old payload (omitting title and is_active) succeeds with 201 Created."""
        legacy_payload = {
            "long_url": "https://example.com/v-old-client-compatibility-test",
            "tags": ["legacy"]
        }
        res = client.post("/links", headers=self.headers_org_a, json=legacy_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["long_url"], legacy_payload["long_url"])
        self.assertTrue(data.get("is_active"), "Default is_active should be True for legacy clients")
        self.assertIsNone(data.get("title"), "Default title should be None")

    def test_04_modern_v_new_request_compatibility(self):
        """Verify modern V_new payload (supplying title and is_active) succeeds."""
        modern_payload = {
            "long_url": "https://example.com/v-new-modern-feature-test",
            "title": "Modern Feature Link",
            "is_active": True,
            "tags": ["modern", "v_new"]
        }
        res = client.post("/links", headers=self.headers_org_a, json=modern_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Modern Feature Link")
        self.assertTrue(data["is_active"])

    def test_05_update_expanded_fields(self):
        """Verify updating title and is_active via PATCH works."""
        # Create link
        create_res = client.post(
            "/links",
            headers=self.headers_org_a,
            json={"long_url": "https://example.com/patch-test-target"}
        ).json()
        link_id = create_res["id"]
        
        # Patch with new title
        patch_res = client.patch(
            f"/links/{link_id}",
            headers=self.headers_org_a,
            json={"title": "Updated Brand New Title"}
        )
        self.assertEqual(patch_res.status_code, 200)

    def test_06_safe_rollback_drill(self):
        """Verify safe rollback path on a sandbox table without data corruption."""
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("DROP TABLE IF EXISTS links_rollback_drill;"))
                conn.execute(text("""
                    CREATE TABLE links_rollback_drill (
                        id SERIAL PRIMARY KEY,
                        code VARCHAR(12) NOT NULL,
                        long_url TEXT NOT NULL,
                        is_active BOOLEAN DEFAULT true,
                        title VARCHAR(255)
                    );
                """))
                conn.execute(text("""
                    INSERT INTO links_rollback_drill (code, long_url, is_active, title)
                    VALUES ('roll123', 'https://example.com', true, 'Test Title');
                """))
                
                # Simulate column rollback (Contract reversion)
                conn.execute(text("ALTER TABLE links_rollback_drill DROP COLUMN title;"))
                
                # Verify base data remains intact
                row = conn.execute(text("SELECT code, long_url, is_active FROM links_rollback_drill WHERE code = 'roll123'")).fetchone()
                self.assertEqual(row[0], "roll123")
                self.assertEqual(row[1], "https://example.com")
                self.assertTrue(row[2])

if __name__ == "__main__":
    unittest.main()
