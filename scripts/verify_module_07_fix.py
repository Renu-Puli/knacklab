"""
Verification Script: Module 07 FIX (Medium - Job Not Idempotent)
Proves that:
1. When a Celery task is processed for the first time, it records the click.
2. When the identical task payload (with the same click_event_id) is re-delivered/retried,
   the worker deduplicates it and does NOT insert a second row in PostgreSQL.
3. Analytics count remains exactly 1.
"""
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath('apps/api'))

import httpx
from sqlalchemy import text
from app.main import app
from app.database import engine
from app.worker import record_click_event_task

API_KEY_A = "test-api-key-org-a"
HEADERS_ORG_A = {"X-API-Key": API_KEY_A}


async def verify():
    print("=" * 70)
    print("MODULE 07 FIX VERIFICATION: Proving Idempotent Click Processing")
    print("=" * 70)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Step 1: Create a short link
        create_res = await client.post(
            "/links",
            json={"long_url": "https://example.com/module07-fix-verification"},
            headers=HEADERS_ORG_A,
        )
        assert create_res.status_code == 201, f"Failed to create link: {create_res.text}"
        link = create_res.json()
        link_id = link["id"]
        code = link["code"]
        print(f"[Step 1] Created short link: code={code}, id={link_id}")

        # Step 2: Baseline analytics
        analytics_init = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        assert analytics_init.status_code == 200
        assert analytics_init.json()["total_clicks"] == 0
        print(f"[Step 2] Baseline analytics verified: total_clicks = 0")

        # Step 3: First attempt
        stable_event_id = f"evt_fix_{uuid.uuid4().hex[:12]}"
        click_payload = {
            "click_event_id": stable_event_id,
            "link_id": link_id,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FixVerify/1.0",
            "referrer": "https://partner-portal.example.com",
            "ip_hash": "c" * 64,
        }
        print(f"\n[Step 3] Processing click event (First Attempt): click_event_id={stable_event_id}")
        res1 = record_click_event_task(click_payload)
        print(f"  -> Worker response: {res1}")
        assert res1["status"] == "recorded"
        assert res1["click_event_id"] == stable_event_id
        assert res1["id"] is not None

        analytics_after_1 = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        count_1 = analytics_after_1.json()["total_clicks"]
        print(f"  -> Analytics count after 1 click: total_clicks = {count_1}")
        assert count_1 == 1

        # Step 4: Redelivery / retry simulation
        print(f"\n[Step 4] Simulating Celery task retry with IDENTICAL payload: click_event_id={stable_event_id}")
        res2 = record_click_event_task(click_payload)
        print(f"  -> Worker response on retry: {res2}")
        assert res2["status"] == "deduplicated", f"Expected deduplicated status, got: {res2}"
        assert res2["click_event_id"] == stable_event_id

        # Step 5: Verify analytics count and DB row count
        analytics_after_2 = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        count_2 = analytics_after_2.json()["total_clicks"]
        print(f"\n[Step 5] Analytics count after simulated retry: total_clicks = {count_2}")
        assert count_2 == 1, f"Expected total_clicks == 1, got {count_2}"

        with engine.connect() as conn:
            total_records_for_link = conn.execute(
                text("SELECT count(*) FROM click_events WHERE link_id = :lid"),
                {"lid": link_id}
            ).scalar()

        print(f"  -> Total click_events rows in DB for link_id {link_id}: {total_records_for_link}")
        assert total_records_for_link == 1, f"Expected 1 DB row, got {total_records_for_link}"

        print("\n" + "=" * 70)
        print("PASS: Idempotency is verified! Duplicate tasks are ignored safely.")
        print("=" * 70)


if __name__ == "__main__":
    import asyncio
    asyncio.run(verify())
