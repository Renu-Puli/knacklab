"""
Module 08: Reproduce slow query patterns, Sort overhead in EXPLAIN ANALYZE,
unoptimized offset pagination, and N+1 query bottlenecks using real tenant data.
"""
import sys
import time
import json
sys.path.insert(0, "apps/api")

from app.database import engine, text

def run_benchmarks():
    results = {}
    with engine.connect() as conn:
        # 1. EXPLAIN ANALYZE for tenant link listing without composite index
        explain_query = text("""
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT * FROM links 
            WHERE created_by = 'org_a' 
            ORDER BY created_at DESC, id DESC 
            LIMIT 20 OFFSET 500;
        """)
        explain_res = conn.execute(explain_query).scalar()
        plan = explain_res[0]["Plan"]
        results["explain_plan_sort"] = {
            "node_type": plan["Node Type"],
            "total_cost": plan["Total Cost"],
            "actual_total_time": plan["Actual Total Time"],
            "has_explicit_sort": "Sort" in json.dumps(plan),
            "plan_summary": f"{plan['Node Type']} (cost={plan['Startup Cost']}..{plan['Total Cost']})"
        }
        
        # 2. Benchmark N+1 vs Single Batch Query
        links = conn.execute(text("SELECT id FROM links WHERE created_by = 'org_a' LIMIT 20")).fetchall()
        link_ids = [l[0] for l in links]
        
        # N+1 pattern: 20 separate count queries
        t0 = time.perf_counter()
        n_plus_1_counts = {}
        for lid in link_ids:
            cnt = conn.execute(text("SELECT count(*) FROM click_events WHERE link_id = :lid"), {"lid": lid}).scalar()
            n_plus_1_counts[lid] = cnt
        t_n_plus_1 = (time.perf_counter() - t0) * 1000
        
        # Batch pattern: 1 single GROUP BY query
        t0 = time.perf_counter()
        batch_counts = {}
        if link_ids:
            batch_res = conn.execute(
                text("SELECT link_id, count(*) FROM click_events WHERE link_id = ANY(:lids) GROUP BY link_id"),
                {"lids": link_ids}
            ).fetchall()
            batch_counts = {r[0]: r[1] for r in batch_res}
        t_batch = (time.perf_counter() - t0) * 1000
        
        results["n_plus_1_benchmark"] = {
            "link_count": len(link_ids),
            "n_plus_1_time_ms": round(t_n_plus_1, 3),
            "batch_time_ms": round(t_batch, 3),
            "speedup_factor": round(t_n_plus_1 / max(t_batch, 0.001), 2)
        }
        
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    run_benchmarks()
