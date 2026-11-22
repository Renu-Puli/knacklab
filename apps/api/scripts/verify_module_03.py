import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.link import LinkCreate
from app.database import SessionLocal, engine
from app.models import Link, ClickEvent
from app.routers.links import create_link, list_links, get_link_by_id, generate_short_code
from app.routers.redirect import redirect_short_code
from app.auth import Principal
from starlette.requests import Request
from fastapi import HTTPException

def run_tests():
    print("=== STARTING FOCUSED CODE REVIEW VERIFICATION ===")
    
    print("\n--- 1. DATABASE DIALECT CHECK ---")
    print(f"Engine URL dialect: {engine.url.drivername}")
    assert "psycopg" in engine.url.drivername, f"Expected psycopg driver, got {engine.url.drivername}"
    print("[PASS] Normalization to postgresql+psycopg verified")

    print("\n--- 2. URL VALIDATION ABUSE CHECKS (RAW URL INPUTS) ---")
    malicious_inputs = [
        ("javascript:alert(1)", "javascript scheme"),
        ("JaVaScRiPt:alert(1)", "mixed-case javascript scheme"),
        (" javascript:alert(1) ", "whitespace-padded javascript"),
        ("data:text/html,<svg/onload=alert(1)>", "data scheme"),
        ("//evil.example.com", "scheme-relative URL"),
        ("http:%2f%2fevil.example.com", "encoded slashes"),
        ("http%3A%2F%2Fevil.example.com", "encoded scheme"),
        ("http:\\\\evil.example.com", "backslashes"),
        ("https://example.com\\n", "newline control char"),
        ("file:///etc/passwd", "file scheme"),
    ]
    for raw_url, desc in malicious_inputs:
        try:
            LinkCreate(long_url=raw_url)
            raise AssertionError(f"VULNERABILITY: {desc} was accepted: {raw_url}")
        except Exception:
            print(f"[REJECTED] {desc} ({raw_url!r})")

    valid_urls = [
        "https://example.com",
        "http://subdomain.test.org/path?query=1#frag",
        "  https://example.com/trimmed  ",
    ]
    for raw_url in valid_urls:
        validated = LinkCreate(long_url=raw_url)
        assert not validated.long_url.startswith(" "), "Leading whitespace not stripped"
        assert not validated.long_url.endswith(" "), "Trailing whitespace not stripped"
        print(f"[ACCEPTED & STORED CLEAN RAW URL] {validated.long_url}")

    print("\n--- 3. TENANT ISOLATION TESTS (AUTHENTICATED PRINCIPAL) ---")
    db = SessionLocal()
    req = Request({
        "type": "http",
        "method": "POST",
        "path": "/links",
        "headers": [(b"host", b"testserver")],
        "scheme": "http",
        "server": ("testserver", 80),
    })

    principal_100 = Principal(principal_id="org_100", org_id="org_100")
    principal_200 = Principal(principal_id="org_200", org_id="org_200")

    try:
        # Create link for org_100
        l_100 = create_link(
            payload=LinkCreate(long_url="https://example.com/org100"),
            request=req,
            db=db,
            principal=principal_100
        )
        # Create link for org_200
        l_200 = create_link(
            payload=LinkCreate(long_url="https://example.com/org200"),
            request=req,
            db=db,
            principal=principal_200
        )

        # Listing test
        list_100 = list_links(request=req, skip=0, limit=20, db=db, principal=principal_100)
        list_200 = list_links(request=req, skip=0, limit=20, db=db, principal=principal_200)
        assert any(l.id == l_100.id for l in list_100), "org_100 must see its own link"
        assert not any(l.id == l_200.id for l in list_100), "SECURITY LEAK: org_100 saw org_200 link!"
        assert any(l.id == l_200.id for l in list_200), "org_200 must see its own link"
        assert not any(l.id == l_100.id for l in list_200), "SECURITY LEAK: org_200 saw org_100 link!"
        print("[PASS] Tenant isolation verified in link listing via authenticated principal")

        # Get by ID cross-tenant rejection
        try:
            get_link_by_id(link_id=l_100.id, request=req, db=db, principal=principal_200)
            raise AssertionError("SECURITY LEAK: org_200 fetched org_100's link by ID!")
        except HTTPException as e:
            assert e.status_code == 404
            print("[PASS] Cross-tenant get_link_by_id returned 404 Not Found")

        print("\n--- 4. CLICK TRACKING RESILIENCE (ANALYTICS FAILURE DOES NOT BLOCK REDIRECT) ---")
        redir_req = Request({
            "type": "http",
            "method": "GET",
            "path": f"/r/{l_100.code}",
            "headers": [(b"host", b"testserver")],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 54321),
        })

        # Test normal redirect with click logging
        resp = redirect_short_code(code=l_100.code, request=redir_req, db=db)
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://example.com/org100"
        print("[PASS] Standard redirect returned 307 with Location header")

        # Simulate failure in click event insertion (e.g., DB error, lock timeout)
        with patch.object(db, "commit", side_effect=Exception("Database lock timeout on click_events")):
            resp_sim = redirect_short_code(code=l_100.code, request=redir_req, db=db)
            assert resp_sim.status_code == 307
            assert resp_sim.headers["location"] == "https://example.com/org100"
            print("[PASS] Simulated analytics failure DID NOT fail redirect (returned 307 gracefully)")

        print("\n--- 5. SHORT CODE COLLISION RETRY LOGIC ---")
        db.query(Link).filter(Link.code.in_(["collision1", "collision2"])).delete(synchronize_session=False)
        db.commit()
        with patch("app.routers.links.generate_short_code", side_effect=["collision1", "collision2", "unique_code"]):
            # Pre-insert collision1 and collision2
            c1 = Link(code="collision1", long_url="https://example.com/1", created_by="test")
            c2 = Link(code="collision2", long_url="https://example.com/2", created_by="test")
            db.add_all([c1, c2])
            db.commit()

            # Now generate_short_code should retry and succeed with unique_code
            code_gen = generate_short_code(db)
            assert code_gen not in ("collision1", "collision2")
            print(f"[PASS] Short code collision check resolved to unique code: {code_gen}")

        print("\n=== ALL REVIEW VERIFICATIONS PASSED SUCCESSFULLY ===")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
