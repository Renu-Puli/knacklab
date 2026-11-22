import sys
sys.path.insert(0, "apps/api")
from app.database import engine, text

with engine.connect() as conn:
    links_cnt = conn.execute(text("SELECT count(*) FROM links")).scalar()
    clicks_cnt = conn.execute(text("SELECT count(*) FROM click_events")).scalar()
    indices = conn.execute(text("""
        SELECT tablename, indexname, indexdef 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        ORDER BY tablename, indexname;
    """)).fetchall()
    print(f"Row counts: links={links_cnt}, click_events={clicks_cnt}")
    print("Current indexes:")
    for idx in indices:
        print(f"  {idx[0]}.{idx[1]}: {idx[2]}")
