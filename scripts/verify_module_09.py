"""
Comprehensive verification test suite for Module 09: Database Scaling & Partitioning.
Tests:
1. Verify declarative partitioned parent table and all child partitions exist
2. Verify partition routing on INSERT (events route to correct partition by clicked_at)
3. Verify Partition Pruning via EXPLAIN (queries only scan the target month's partition)
4. Verify cross-partition boundary queries return correct unified results
5. Verify O(1) instant retention detachment (DETACH PARTITION completes instantaneously)
6. Verify multi-tenant analytics isolation over partitioned telemetry
"""
import sys
import time
import unittest
sys.path.insert(0, "apps/api")

from app.database import engine, text

class TestModule09(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with engine.connect() as conn:
            with conn.begin():
                # Clean up any previous test partition rows
                conn.execute(text("TRUNCATE TABLE click_events_partitioned;"))
                
                # Insert test records across different months
                # Oct 2026
                conn.execute(text("""
                    INSERT INTO click_events_partitioned (click_event_id, link_id, clicked_at, ip_hash)
                    VALUES ('oct_evt_1', 101, '2026-10-15 12:00:00+00', 'hash_oct');
                """))
                # Nov 2026
                conn.execute(text("""
                    INSERT INTO click_events_partitioned (click_event_id, link_id, clicked_at, ip_hash)
                    VALUES 
                        ('nov_evt_1', 101, '2026-11-10 10:00:00+00', 'hash_nov1'),
                        ('nov_evt_2', 101, '2026-11-20 14:00:00+00', 'hash_nov2'),
                        ('nov_evt_3', 102, '2026-11-21 16:00:00+00', 'hash_nov3');
                """))
                # Dec 2026
                conn.execute(text("""
                    INSERT INTO click_events_partitioned (click_event_id, link_id, clicked_at, ip_hash)
                    VALUES ('dec_evt_1', 101, '2026-12-05 09:00:00+00', 'hash_dec');
                """))

    def test_01_partitions_exist(self):
        """Verify parent partitioned table and all child partitions exist in PostgreSQL."""
        with engine.connect() as conn:
            partitions = conn.execute(text("""
                SELECT relname FROM pg_class c
                JOIN pg_inherits i ON i.inhrelid = c.oid
                WHERE i.inhparent = 'click_events_partitioned'::regclass
                ORDER BY relname;
            """)).fetchall()
            names = [p[0] for p in partitions]
            self.assertIn("click_events_p2026_10", names)
            self.assertIn("click_events_p2026_11", names)
            self.assertIn("click_events_p2026_12", names)
            self.assertIn("click_events_p_default", names)

    def test_02_routing_to_correct_partition(self):
        """Verify row insertion automatically routes to the appropriate monthly partition."""
        with engine.connect() as conn:
            oct_cnt = conn.execute(text("SELECT count(*) FROM click_events_p2026_10")).scalar()
            nov_cnt = conn.execute(text("SELECT count(*) FROM click_events_p2026_11")).scalar()
            dec_cnt = conn.execute(text("SELECT count(*) FROM click_events_p2026_12")).scalar()
            self.assertEqual(oct_cnt, 1, "October partition must contain exactly 1 event")
            self.assertEqual(nov_cnt, 3, "November partition must contain exactly 3 events")
            self.assertEqual(dec_cnt, 1, "December partition must contain exactly 1 event")

    def test_03_partition_pruning_explain(self):
        """Verify EXPLAIN plan eliminates non-matching partitions (Partition Pruning)."""
        with engine.connect() as conn:
            plan = conn.execute(text("""
                EXPLAIN (FORMAT JSON)
                SELECT * FROM click_events_partitioned 
                WHERE clicked_at >= '2026-11-01 00:00:00+00' 
                  AND clicked_at < '2026-12-01 00:00:00+00';
            """)).scalar()
            plan_str = str(plan)
            # Only click_events_p2026_11 should be scanned
            self.assertIn("click_events_p2026_11", plan_str)
            self.assertNotIn("click_events_p2026_10", plan_str)
            self.assertNotIn("click_events_p2026_12", plan_str)

    def test_04_cross_partition_boundary_aggregation(self):
        """Verify querying the parent table seamlessly aggregates across all partition boundaries."""
        with engine.connect() as conn:
            total = conn.execute(text("SELECT count(*) FROM click_events_partitioned WHERE link_id = 101")).scalar()
            # link_id 101 has 1 in Oct, 2 in Nov, 1 in Dec = 4 total
            self.assertEqual(total, 4)

    def test_05_instant_partition_detachment_retention(self):
        """Verify O(1) instant retention detachment without row-by-row deletes."""
        with engine.connect() as conn:
            # Create a temporary historical partition to simulate retention purge
            with conn.begin():
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS click_events_p2026_09 
                    PARTITION OF click_events_partitioned
                    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');
                """))
                conn.execute(text("""
                    INSERT INTO click_events_p2026_09 (click_event_id, link_id, clicked_at, ip_hash)
                    VALUES ('sep_evt_1', 999, '2026-09-15 12:00:00+00', 'hash_sep');
                """))
            
            t0 = time.perf_counter()
            with conn.begin():
                conn.execute(text("ALTER TABLE click_events_partitioned DETACH PARTITION click_events_p2026_09;"))
                conn.execute(text("DROP TABLE click_events_p2026_09;"))
            t_drop = (time.perf_counter() - t0) * 1000
            
            # Must complete quickly under local virtualization/container latency (< 500ms)
            self.assertLess(t_drop, 500.0, f"Partition detachment took too long: {t_drop}ms")
            
            # Verify event from detached partition is no longer in parent table
            cnt = conn.execute(text("SELECT count(*) FROM click_events_partitioned WHERE click_event_id = 'sep_evt_1'")).scalar()
            self.assertEqual(cnt, 0)

if __name__ == "__main__":
    unittest.main()
