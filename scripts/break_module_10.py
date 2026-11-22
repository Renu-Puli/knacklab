"""
Module 10 Break: Reproduce an unsafe breaking database migration scenario.
Simulates an unsafe NOT NULL constraint addition without defaults that breaks legacy app inserts.
"""
import sys
import json
sys.path.insert(0, "apps/api")

from app.database import engine, text

def run_break_experiment():
    results = {}
    with engine.connect() as conn:
        # Create an isolated sandbox table mirroring links to demonstrate unsafe migration
        with conn.begin():
            conn.execute(text("DROP TABLE IF EXISTS links_migration_drill;"))
            conn.execute(text("""
                CREATE TABLE links_migration_drill (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(12) UNIQUE NOT NULL,
                    long_url TEXT NOT NULL,
                    created_by VARCHAR NOT NULL
                );
            """))
            # Insert existing legacy row
            conn.execute(text("""
                INSERT INTO links_migration_drill (code, long_url, created_by)
                VALUES ('drill123', 'https://example.com', 'org_drill');
            """))

        # Scenario 1: Attempting an unsafe migration (ADD COLUMN NOT NULL without default)
        unsafe_migration_error = None
        try:
            with conn.begin():
                conn.execute(text("""
                    ALTER TABLE links_migration_drill 
                    ADD COLUMN is_active BOOLEAN NOT NULL;
                """))
        except Exception as e:
            unsafe_migration_error = str(e)
            
        results["unsafe_migration_on_populated_table"] = {
            "error_type": "NotNullViolation / TableLockError",
            "error_message": unsafe_migration_error.split("\n")[0] if unsafe_migration_error else "None",
            "impact": "Migration fails immediately during deployment or locks entire table while checking existing rows"
        }

        # Scenario 2: If added with default, but legacy app doesn't know about it, what if an old app writes NULL?
        with conn.begin():
            # Add with NOT NULL and default
            conn.execute(text("""
                ALTER TABLE links_migration_drill 
                ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true;
            """))
            
        # Legacy app tries to insert a row where client-supplied or deserialized payload sends explicit NULL
        v_old_insert_error = None
        try:
            with conn.begin():
                conn.execute(text("""
                    INSERT INTO links_migration_drill (code, long_url, created_by, is_active)
                    VALUES ('drill456', 'https://example.com/2', 'org_drill', NULL);
                """))
        except Exception as e:
            v_old_insert_error = str(e)

        results["v_old_explicit_null_insertion"] = {
            "error_type": "IntegrityError",
            "error_message": v_old_insert_error.split("\n")[0] if v_old_insert_error else "None",
            "impact": "Legacy app crashes if payloads omit or pass unpopulated null attributes"
        }

    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    run_break_experiment()
