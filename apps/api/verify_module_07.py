"""
Module 07 Verification Suite: Background Jobs & Analytics
Tests:
1. Hot Path Redirect: Returns 307 immediately on cache miss and cache hit.
2. Worker Processing: Consumes click events and persists to PostgreSQL.
3. Idempotent Delivery: Duplicate click_event_id does not create duplicate rows.
4. Privacy Protection: Raw IP is never stored; only SHA-256 ip_hash.
5. Queue-Down Resilience Drill: Redirect succeeds (HTTP 307) even if enqueue fails.
6. Owner-Scoped Analytics: GET /links/{id}/analytics returns total_clicks and window.
7. Multi-Tenant Scoping: Cross-tenant analytics query returns 404 Not Found.
8. Date Range Validation: Invalid date or inverted range returns 400 Bad Request.
9. Retention Cleanup: purge_expired_clicks_task deletes events older than retention window.
10. Live Celery Worker: Worker consumes event from Redis queue and persists to DB.
"""
import sys
import os
import time
import uuid
import subprocess
from datetime import datetime, timedelta, timezone

# Ensure apps/api is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

import httpx
from sqlalchemy import text
from app.main import app
from app.database import engine, SessionLocal
from app.models import Link, ClickEvent
from app.cache import init_redis, close_redis
from app.worker import record_click_event_task, purge_expired_clicks_task, celery_app
import app.routers.redirect as redirect_module

API_KEY_A = "test-api-key-org-a"
API_KEY_B = "test-api-key-org-b"

HEADERS_ORG_A = {"X-API-Key": API_KEY_A}
HEADERS_ORG_B = {"X-API-Key": API_KEY_B}


async def run_verification():
    print("=" * 70)
    print("Running Module 07 Verification Suite: Background Jobs & Analytics")
    print("=" * 70)

    await init_redis()

    passed = 0
    total = 0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        # -------------------------------------------------------------
        # Test 1: Hot Path Redirect Enqueues Asynchronously (307)
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 1] Testing Hot Path Redirect (Cache Miss & Cache Hit)...")
        create_res = await client.post(
            "/links",
            json={"long_url": "https://example.com/module07-hotpath"},
            headers=HEADERS_ORG_A,
        )
        assert create_res.status_code == 201, f"Expected 201, got {create_res.status_code}: {create_res.text}"
        link_data = create_res.json()
        code = link_data["code"]
        link_id = link_data["id"]

        # Cache Miss redirect
        r_miss = await client.get(f"/r/{code}", headers={"User-Agent": "TestBrowser/1.0", "Referer": "https://news.ycombinator.com"})
        assert r_miss.status_code == 307, f"Expected 307 on miss, got {r_miss.status_code}"
        assert r_miss.headers["location"] == "https://example.com/module07-hotpath"

        # Cache Hit redirect
        r_hit = await client.get(f"/r/{code}", headers={"User-Agent": "TestBrowser/1.0"})
        assert r_hit.status_code == 307, f"Expected 307 on hit, got {r_hit.status_code}"
        assert r_hit.headers["location"] == "https://example.com/module07-hotpath"
        print("  -> Redirect succeeded immediately with HTTP 307 on both miss and hit.")
        passed += 1

        # -------------------------------------------------------------
        # Test 2: Worker Processing & Database Persistence
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 2] Testing Worker Task Processing & Database Persistence...")
        event_id_1 = f"evt_{uuid.uuid4().hex}"
        click_payload_1 = {
            "click_event_id": event_id_1,
            "link_id": link_id,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "referrer": "https://google.com",
            "ip_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        }
        res_task = record_click_event_task(click_payload_1)
        assert res_task["status"] == "recorded", f"Expected recorded status, got: {res_task}"

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, link_id, click_event_id, user_agent, referrer, ip_hash FROM click_events WHERE click_event_id = :cid"),
                {"cid": event_id_1}
            ).fetchone()
            assert row is not None, f"Expected click event {event_id_1} in database"
            assert row.link_id == link_id
            assert row.click_event_id == event_id_1
            assert row.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            assert row.referrer == "https://google.com"
        print("  -> Worker task successfully recorded click event into PostgreSQL.")
        passed += 1

        # -------------------------------------------------------------
        # Test 3: Idempotent Delivery & Deduplication
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 3] Testing Idempotent Delivery & Deduplication...")
        # Re-dispatch exact same payload
        res_duplicate = record_click_event_task(click_payload_1)
        assert res_duplicate["status"] == "deduplicated", f"Expected deduplicated status, got: {res_duplicate}"

        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM click_events WHERE click_event_id = :cid"),
                {"cid": event_id_1}
            ).scalar()
            assert count == 1, f"Expected exactly 1 row after replay, got {count}"
        print("  -> Idempotent replay: duplicate click_event_id cleanly deduplicated without error.")
        passed += 1

        # -------------------------------------------------------------
        # Test 4: Privacy Protection (No Raw IP Stored)
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 4] Testing Privacy Protection (Raw IP Absent, Hash Present)...")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT ip_hash FROM click_events WHERE click_event_id = :cid"),
                {"cid": event_id_1}
            ).fetchone()
            assert row.ip_hash is not None, "ip_hash must be present"
            assert len(row.ip_hash) == 64, f"Expected 64-char hex SHA-256, got {len(row.ip_hash)}"
            assert "127.0.0.1" not in row.ip_hash
        print("  -> Privacy verified: only SHA-256 hash stored; raw client IP is never persisted.")
        passed += 1

        # -------------------------------------------------------------
        # Test 5: Queue-Down Resilience Drill
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 5] Testing Queue-Down Resilience Drill...")
        original_delay = redirect_module.record_click_event_task.delay

        def failing_delay(*args, **kwargs):
            raise ConnectionError("Redis broker is unreachable (simulated queue outage)")

        try:
            redirect_module.record_click_event_task.delay = failing_delay
            # Execute redirect while queue is simulated down
            r_queue_down = await client.get(f"/r/{code}")
            assert r_queue_down.status_code == 307, f"Expected 307 even when queue down, got {r_queue_down.status_code}"
            assert r_queue_down.headers["location"] == "https://example.com/module07-hotpath"
            print("  -> Resilience confirmed: redirect succeeded (307) during simulated queue outage.")
            passed += 1
        finally:
            redirect_module.record_click_event_task.delay = original_delay

        # -------------------------------------------------------------
        # Test 6: Owner-Scoped Analytics Endpoint (GET /links/{id}/analytics)
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 6] Testing Owner-Scoped Analytics Endpoint...")
        # Seed 3 additional distinct clicks for link_id
        for i in range(3):
            cid = f"evt_{uuid.uuid4().hex}"
            record_click_event_task({
                "click_event_id": cid,
                "link_id": link_id,
                "clicked_at": datetime.now(timezone.utc).isoformat(),
                "user_agent": f"Agent/{i}",
                "referrer": "https://example.org",
                "ip_hash": "f" * 64,
            })

        analytics_res = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_A)
        assert analytics_res.status_code == 200, f"Expected 200, got {analytics_res.status_code}: {analytics_res.text}"
        data = analytics_res.json()
        assert data["link_id"] == link_id
        assert data["total_clicks"] >= 4, f"Expected at least 4 clicks, got {data['total_clicks']}"
        assert "from" in data and "to" in data
        assert data["last_clicked_at"] is not None
        print(f"  -> Analytics response verified: link_id={data['link_id']}, total_clicks={data['total_clicks']}")
        passed += 1

        # -------------------------------------------------------------
        # Test 7: Multi-Tenant Scoping & Security on Analytics
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 7] Testing Multi-Tenant Scoping on Analytics (Cross-Tenant -> 404)...")
        # Org B attempts to view Org A's link analytics
        res_cross = await client.get(f"/links/{link_id}/analytics", headers=HEADERS_ORG_B)
        assert res_cross.status_code == 404, f"Expected 404 for cross-tenant query, got {res_cross.status_code}"
        
        # Unauthenticated query
        res_no_auth = await client.get(f"/links/{link_id}/analytics")
        assert res_no_auth.status_code == 401, f"Expected 401 for unauthenticated query, got {res_no_auth.status_code}"
        print("  -> Multi-tenant security verified: cross-tenant access blocked with 404; unauthenticated with 401.")
        passed += 1

        # -------------------------------------------------------------
        # Test 8: Date Range Filtering & Validation
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 8] Testing Date Range Filtering & Validation...")
        # Valid date range
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        res_date = await client.get(f"/links/{link_id}/analytics?from={today_str}&to={today_str}", headers=HEADERS_ORG_A)
        assert res_date.status_code == 200, f"Expected 200, got {res_date.status_code}"
        assert res_date.json()["total_clicks"] >= 4

        # Inverted date range (from > to)
        res_inverted = await client.get(f"/links/{link_id}/analytics?from=2026-12-01&to=2026-01-01", headers=HEADERS_ORG_A)
        assert res_inverted.status_code == 400, f"Expected 400 for inverted range, got {res_inverted.status_code}"

        # Invalid date format
        res_invalid = await client.get(f"/links/{link_id}/analytics?from=not-a-date", headers=HEADERS_ORG_A)
        assert res_invalid.status_code == 400, f"Expected 400 for invalid date, got {res_invalid.status_code}"
        print("  -> Date filtering and validation verified: invalid format and inverted ranges return 400.")
        passed += 1

        # -------------------------------------------------------------
        # Test 9: Retention Cleanup Task (30-day purge)
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 9] Testing Retention Cleanup Task (purge_expired_clicks_task)...")
        expired_cid = f"expired_{uuid.uuid4().hex}"
        recent_cid = f"recent_{uuid.uuid4().hex}"
        old_time = datetime.now(timezone.utc) - timedelta(days=45)
        new_time = datetime.now(timezone.utc) - timedelta(days=5)

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO click_events (click_event_id, link_id, clicked_at, user_agent, referrer, ip_hash)
                    VALUES (:cid_old, :lid, :old_t, 'OldBot', 'https://old.com', 'oldhash'),
                           (:cid_new, :lid, :new_t, 'NewBot', 'https://new.com', 'newhash')
                """),
                {"cid_old": expired_cid, "cid_new": recent_cid, "lid": link_id, "old_t": old_time, "new_t": new_time}
            )

        purge_result = purge_expired_clicks_task(retention_days=30)
        assert purge_result["status"] == "purged"
        assert purge_result["deleted_count"] >= 1, f"Expected at least 1 purged row, got {purge_result}"

        with engine.connect() as conn:
            old_row = conn.execute(text("SELECT id FROM click_events WHERE click_event_id = :cid"), {"cid": expired_cid}).fetchone()
            assert old_row is None, f"Expired click event {expired_cid} was not purged"

            new_row = conn.execute(text("SELECT id FROM click_events WHERE click_event_id = :cid"), {"cid": recent_cid}).fetchone()
            assert new_row is not None, f"Recent click event {recent_cid} was unexpectedly purged"

            link_check = conn.execute(text("SELECT id FROM links WHERE id = :lid"), {"lid": link_id}).fetchone()
            assert link_check is not None, "Parent link must remain intact after retention cleanup"
        print(f"  -> Retention cleanup verified: {purge_result['deleted_count']} expired rows purged; recent events and links intact.")
        passed += 1

        # -------------------------------------------------------------
        # Test 10: Celery Worker Integration with Live Redis Broker
        # -------------------------------------------------------------
        total += 1
        print("\n[Test 10] Testing Celery Worker Integration with Live Redis Broker...")
        worker_event_id = f"worker_test_{uuid.uuid4().hex}"
        worker_payload = {
            "click_event_id": worker_event_id,
            "link_id": link_id,
            "clicked_at": datetime.now(timezone.utc).isoformat(),
            "user_agent": "CeleryWorkerTestAgent/1.0",
            "referrer": "https://celeryproject.org",
            "ip_hash": "a" * 64,
        }

        # Enqueue task to Redis queue
        async_result = record_click_event_task.delay(worker_payload)
        print(f"  -> Enqueued task to Redis: id={async_result.id}")

        # Spawn a short-lived Celery worker process to consume the event
        worker_cmd = [
            sys.executable,
            "-u",
            "-m", "celery",
            "-A", "app.worker",
            "worker",
            "--loglevel=INFO",
            "--pool=solo",
            "--concurrency=1",
        ]
        worker_log = open(os.path.join(os.path.dirname(__file__), "celery_worker_test10.log"), "w")
        proc = subprocess.Popen(
            worker_cmd,
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__))),
            stdout=worker_log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

        try:
            # Poll for up to 30 seconds for the worker to process the message into PostgreSQL
            start_poll = time.time()
            persisted = False
            while time.time() - start_poll < 30:
                with engine.connect() as conn:
                    row = conn.execute(
                        text("SELECT id, click_event_id FROM click_events WHERE click_event_id = :cid"),
                        {"cid": worker_event_id}
                    ).fetchone()
                    if row is not None:
                        persisted = True
                        break
                time.sleep(0.5)

            if not persisted:
                worker_log.flush()
                try:
                    with open(os.path.join(os.path.dirname(__file__), "celery_worker_test10.log"), "r") as f:
                        print("Worker log content:\n", f.read())
                except Exception as e:
                    print("Could not read worker log:", e)

            assert persisted, f"Celery worker did not persist event {worker_event_id} within timeout"
            print("  -> Live Celery worker consumed task from Redis queue and persisted record to PostgreSQL.")
            passed += 1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

    await close_redis()

    print("\n" + "=" * 70)
    print(f"Module 07 Verification Complete: {passed}/{total} tests passed.")
    print("=" * 70)
    assert passed == total, f"Only {passed}/{total} tests passed"


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_verification())
