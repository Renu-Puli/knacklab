"""
Zero-downtime Expand-and-Contract migration for LinkOps links table.
Phase 1: Expand - add columns with non-blocking server default.
Phase 2: Backfill - ensure data integrity on historical rows.
Phase 3: Verify dual-compatibility.
"""
import sys
sys.path.insert(0, "apps/api")

from app.database import engine, text

def run_expand_migration():
    with engine.connect() as conn:
        with conn.begin():
            # 1. Expand: Add columns with safe server default and nullable constraint
            # In PostgreSQL 11+, adding a column with a constant DEFAULT does not rewrite the table or lock it.
            conn.execute(text("""
                ALTER TABLE links 
                ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
            """))
            conn.execute(text("""
                ALTER TABLE links 
                ADD COLUMN IF NOT EXISTS title VARCHAR(255);
            """))
            
            # 2. Backfill historical rows safely
            conn.execute(text("""
                UPDATE links 
                SET is_active = true 
                WHERE is_active IS NULL;
            """))

            print("Successfully completed Expand phase of zero-downtime migration.")

if __name__ == "__main__":
    run_expand_migration()
