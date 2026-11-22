"""
Implementation script for Module 09: Declarative Range Partitioning for Click Telemetry.
Creates click_events_partitioned and demonstrates partition pruning and instant partition drop.
"""
import sys
sys.path.insert(0, "apps/api")

from app.database import engine, text

def setup_partitioning():
    with engine.connect() as conn:
        with conn.begin():
            # 1. Create parent partitioned table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS click_events_partitioned (
                    id SERIAL,
                    click_event_id VARCHAR(64) NOT NULL,
                    link_id INTEGER NOT NULL,
                    clicked_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    user_agent VARCHAR,
                    referrer VARCHAR,
                    ip_hash VARCHAR(64),
                    PRIMARY KEY (id, clicked_at)
                ) PARTITION BY RANGE (clicked_at);
            """))
            
            # 2. Create monthly range partitions
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS click_events_p2026_10 
                PARTITION OF click_events_partitioned
                FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS click_events_p2026_11 
                PARTITION OF click_events_partitioned
                FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS click_events_p2026_12 
                PARTITION OF click_events_partitioned
                FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');
            """))
            
            # Default partition for safety
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS click_events_p_default 
                PARTITION OF click_events_partitioned DEFAULT;
            """))
            
            # 3. Create indexes on each partition via parent table
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_cep_link_clicked 
                ON click_events_partitioned (link_id, clicked_at DESC);
            """))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_cep_click_event_id 
                ON click_events_partitioned (click_event_id);
            """))

            print("Successfully initialized declarative partitioning schema for Module 09.")

if __name__ == "__main__":
    setup_partitioning()
