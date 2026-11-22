"""
Migration script for Module 08: Add composite indexes for high-performance multi-tenant queries.
"""
import sys
sys.path.insert(0, "apps/api")

from app.database import engine, text

def apply_indexes():
    with engine.connect() as conn:
        with conn.begin():
            # 1. Composite index for tenant listing, sorting, and keyset pagination
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_links_tenant_created 
                ON links (created_by, created_at DESC, id DESC);
            """))
            # 2. Composite index for link click analytics date-range scanning
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_click_events_link_clicked 
                ON click_events (link_id, clicked_at DESC);
            """))
            # 3. Trigram/B-Tree index for search queries on tags and code
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_links_tags 
                ON links (tags);
            """))
            print("Successfully applied Module 08 composite indexes.")

if __name__ == "__main__":
    apply_indexes()
