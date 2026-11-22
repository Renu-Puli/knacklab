import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# Add apps/api to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from app.schemas.link import validate_future_datetime, LinkCreate
from app.main import app
from app.models import Link
from app.database import SessionLocal
from starlette.testclient import TestClient

def test_validator_cases():
    print("=== 1. Testing validate_future_datetime() Unit Tests ===")
    now_utc = datetime.now(timezone.utc)

    # 1. Timezone-aware UTC datetime
    future_utc = now_utc + timedelta(hours=2)
    val_utc = validate_future_datetime(future_utc)
    assert val_utc == future_utc
    assert val_utc.tzinfo == timezone.utc
    print("  [PASS] Test 1: Timezone-aware UTC datetime remains correctly handled.")

    # 2. Timezone-aware non-UTC datetime (e.g. Asia/Kolkata +05:30)
    ist = ZoneInfo("Asia/Kolkata")
    future_ist = (now_utc + timedelta(hours=2)).astimezone(ist)
    val_ist = validate_future_datetime(future_ist)
    assert val_ist == future_ist
    assert val_ist.tzinfo is not None
    assert abs((val_ist - now_utc).total_seconds() - 7200) < 1.0
    print("  [PASS] Test 2: Timezone-aware non-UTC datetime retains correct instant.")

    # 3. Naive future datetime normalized to UTC and returned timezone-aware
    future_naive = datetime(2099, 1, 1, 12, 0, 0)
    val_naive = validate_future_datetime(future_naive)
    assert val_naive is not None
    assert val_naive.tzinfo == timezone.utc
    assert val_naive.year == 2099
    assert val_naive.month == 1
    assert val_naive.day == 1
    assert val_naive.hour == 12
    print("  [PASS] Test 3: Naive future datetime is normalized to UTC and returned timezone-aware.")

    # 4. Naive past datetime is rejected
    past_naive = datetime(2020, 1, 1, 12, 0, 0)
    try:
        validate_future_datetime(past_naive)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "expires_at must be in the future" in str(e)
        print("  [PASS] Test 4: Naive past datetime is rejected.")

    # 5. None returns None
    assert validate_future_datetime(None) is None
    print("  [PASS] Test 5: None input safely returns None.")

def test_pydantic_schema_normalization():
    print("\n=== 2. Testing Pydantic Schema LinkCreate Normalization ===")
    # Naive ISO string input
    payload_naive = LinkCreate(
        long_url="https://example.com/naive-test",
        expires_at="2099-06-01T15:30:00"
    )
    assert payload_naive.expires_at is not None
    assert payload_naive.expires_at.tzinfo == timezone.utc
    print(f"  [PASS] Naive ISO string parsed and normalized to: {payload_naive.expires_at.isoformat()}")

def test_api_redirect_behavior():
    print("\n=== 3. Testing API Link Expiry & Redirect Behavior ===")
    client = TestClient(app)
    db = SessionLocal()

    # 1. Link with future expiration allows redirect (307)
    future_time = datetime.now(timezone.utc) + timedelta(hours=5)
    link_future = Link(
        code="exp_fut",
        long_url="https://example.com/future-target",
        created_by="org_a",
        expires_at=future_time
    )
    db.merge(link_future)
    db.commit()

    resp_future = client.get("/r/exp_fut", follow_redirects=False)
    assert resp_future.status_code in (302, 307)
    assert resp_future.headers.get("location") == "https://example.com/future-target"
    print(f"  [PASS] Future expiration allows redirect: status {resp_future.status_code}")

    # 2. Expired link returns 410
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    link_past = Link(
        code="exp_pst",
        long_url="https://example.com/past-target",
        created_by="org_a",
        expires_at=past_time
    )
    db.merge(link_past)
    db.commit()

    resp_past = client.get("/r/exp_pst", follow_redirects=False)
    assert resp_past.status_code == 410
    print(f"  [PASS] Expired link returns HTTP {resp_past.status_code} Gone.")

    # 3. Clean up test records
    db.query(Link).filter(Link.code.in_(["exp_fut", "exp_pst"])).delete()
    db.commit()

if __name__ == "__main__":
    test_validator_cases()
    test_pydantic_schema_normalization()
    test_api_redirect_behavior()
    print("\n=== ALL BUG #4 UNIT & INTEGRATION TESTS PASSED ===")
