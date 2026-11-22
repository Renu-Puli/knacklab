"""
Reproduction Script: Module 07 BREAK (Medium - Job Not Idempotent)
Symptom:
When a Celery task is retried or replayed with the exact same event payload,
the worker inserts a duplicate record into PostgreSQL, causing analytics double-counting.
"""
import sys
import os
import uuid
from datetime import datetime, timezone

# Ensure apps/api is on sys.path
sys.path.insert(0, os.path.abspath('apps/api'))

import httpx
from sqlalchemy import text
from app.main import app
from app.database import engine
from app.worker import record_click_event_task

API_KEY_A = "test-api-key-org-a"
HEADERS_ORG_A = {"X-API-Key": API_KEY_A}


async def reproduce():
    print("=" * 70)
    print("MODULE 07 BREAK REPRODUCTION: Medium – Job Not Idempotent (Duplicates)")
    print("=" * 70)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Step 1: Create a short link
        create_res = await client.post(
            "/links",
            json={"long_url": "https://example.com/module07-break-repro"},
            headers=HEADERS_ORG_A,
        )
        assert create_res.status_code == 201, f"Failed to create link: {create_res.text}"
        link = create_res.json()
        link_id = link["id"]
        code = link["code"]
        print(f"[Step 1] Created short link: code={code}, id={link_id}")

        # Step 2: Check baseline analytics
        analytics_init = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        assert analytics_init.status_code == 200
        print(f"[Step 2] Baseline analytics: total_clicks = {analytics_init.json()['total_clicks']}")

        # Step 3: Worker processes click event (first delivery)
        stable_event_id = f"evt_break_{uuid.uuid4().hex[:12]}"
        click_payload = {
            "click_event_id": stable_event_id,
            "link_id": link_id,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BreakTest/1.0",
            "referrer": "https://partner-portal.example.com",
            "ip_hash": "b" * 64,
        }
        print(f"\n[Step 3] Processing click event (First Attempt): click_event_id={stable_event_id}")
        res1 = record_click_event_task(click_payload)
        print(f"  -> Worker response: {res1}")

        analytics_after_1 = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        count_1 = analytics_after_1.json()["total_clicks"]
        print(f"  -> Analytics count after 1 click: total_clicks = {count_1}")

        # Step 4: Simulate Celery task redelivery / retry with exact same payload
        print(f"\n[Step 4] Simulating Celery task retry/redelivery with IDENTICAL payload...")
        print(f"  -> Re-dispatching click_event_id={stable_event_id}")
        res2 = record_click_event_task(click_payload)
        print(f"  -> Worker response: {res2}")

        # Step 5: Check analytics and database state for duplicate count
        analytics_after_2 = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        count_2 = analytics_after_2.json()["total_clicks"]
        print(f"\n[Step 5] Analytics count after simulated retry: total_clicks = {count_2}")

        with engine.connect() as conn:
            total_records_for_link = conn.execute(
                text("SELECT count(*) FROM click_events WHERE link_id = :lid"),
                {"lid": link_id}
            ).scalar()

        print(f"  -> Total click_events rows in DB for link_id {link_id}: {total_records_for_link}")

        # Failure verification
        print("\n" + "-" * 70)
        print("REPRODUCTION RESULT:")
        if count_2 > 1:
            print(f"FAILURE CONFIRMED: Job is NOT idempotent!")
            print(f"A single click event was processed twice on retry, resulting in {count_2} recorded clicks.")
            print(f"Expected behavior: total_clicks should remain 1 because click_event_id was identical.")
            print(f"Observed behavior: duplicate record was inserted, inflating analytics metrics.")
            print("-" * 70)
        else:
            print(f"UNEXPECTED: Job was deduplicated (count = {count_2}). Bug was not reproduced.")
            print("-" * 70)
            sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(reproduce())
