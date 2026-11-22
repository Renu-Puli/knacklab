"""
Module 09 Break: Reproduce unpartitioned table scan bloat and costly retention purge
vs. declarative partitioning with partition pruning and instant DDL detachment.
"""
import sys
import time
import json
sys.path.insert(0, "apps/api")

from app.database import engine, text

def run_break_experiment():
    results = {}
    with engine.connect() as conn:
        with conn.begin():
            # 1. Measure cost of row-by-row DELETE on unpartitioned table
            # Insert 500 dummy click events for demonstration
            conn.execute(text("""
                INSERT INTO click_events (click_event_id, link_id, clicked_at, user_agent, ip_hash)
                SELECT 
                    'dummy_evt_' || i,
                    (SELECT id FROM links LIMIT 1),
                    NOW() - INTERVAL '45 days',
                    'test_agent',
                    'hash_dummy'
                FROM generate_series(1, 500) AS i
                ON CONFLICT (click_event_id) DO NOTHING;
            """))
            
            t0 = time.perf_counter()
            del_res = conn.execute(text("DELETE FROM click_events WHERE clicked_at < NOW() - INTERVAL '30 days'"))
            t_delete = (time.perf_counter() - t0) * 1000
            
            results["unpartitioned_delete"] = {
                "deleted_rows": del_res.rowcount,
                "time_ms": round(t_delete, 3),
                "mechanism": "Sequential scan + tuple dead-marking (requires VACUUM)"
            }
            
            # 2. Measure EXPLAIN scan without partition pruning on single massive table
            explain_res = conn.execute(text("""
                EXPLAIN (FORMAT JSON)
                SELECT count(*) FROM click_events 
                WHERE clicked_at >= '2026-11-01' AND clicked_at < '2026-11-30';
            """)).scalar()
            
            results["unpartitioned_explain"] = {
                "plan_node": explain_res[0]["Plan"]["Node Type"],
                "scanned_tables": "click_events (monolithic)",
                "total_cost": explain_res[0]["Plan"]["Total Cost"]
            }

    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    run_break_experiment()
