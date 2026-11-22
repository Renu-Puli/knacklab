"""
Module 03: Reproduction Science — STEP 3: BUILD
Reproduction Harness: Concurrent Redirect Stress Test (repro_race.py)

Objective:
Controlled synthetic reproduction script to test the concurrency hypothesis (Candidate 3)
for intermittent HTTP 500 errors on popular short links.

Usage:
  python scripts/repro_race.py [--concurrency 10] [--code <short_code>] [--base-url <url>]

Environment / Mode:
  - Synthetic test data only (no customer tokens, secrets, or PII).
  - Supports live HTTP servers (e.g., http://localhost:8000) or direct ASGI in-process transport.
"""

import argparse
import asyncio
import os
import sys
import uuid
from typing import Dict, Any, List

# Ensure apps/api is importable
API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api"))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

import httpx
from app.main import app
from app.database import SessionLocal
from app.models import Link


def ensure_synthetic_test_link(code: str) -> Link:
    """Ensure a synthetic short link exists for the reproduction experiment."""
    db = SessionLocal()
    try:
        link = db.query(Link).filter(Link.code == code).first()
        if not link:
            link = Link(
                code=code,
                long_url=f"https://example.com/synthetic-destination-{uuid.uuid4().hex[:6]}",
                created_by="synthetic_tenant_repro",
            )
            db.add(link)
            db.commit()
            db.refresh(link)
            print(f"[REPRO SETUP] Created synthetic link: code='{link.code}', id={link.id}")
        else:
            print(f"[REPRO SETUP] Using existing synthetic link: code='{link.code}', id={link.id}")
        return link
    finally:
        db.close()


async def send_single_redirect(client: httpx.AsyncClient, url: str) -> int:
    """Send a single redirect request without following redirects, returning the status code."""
    resp = await client.get(url, follow_redirects=False)
    return resp.status_code


async def run_concurrent_repro(
    base_url: str | None,
    short_code: str,
    concurrency: int,
    use_asgi: bool = False
) -> Dict[str, Any]:
    """
    Fire multiple simultaneous HTTP requests against the exact same short code
    to test the concurrency race condition hypothesis.
    """
    target_path = f"/r/{short_code}"

    print("=" * 70)
    print("MODULE 03: REPRODUCTION SCIENCE — SYNTHETIC REPRO HARNESS")
    print(f"Target Short Code : {short_code}")
    print(f"Concurrency Level : {concurrency} simultaneous requests")
    print(f"Execution Mode    : {'ASGI In-Process Transport' if use_asgi else f'HTTP Loopback ({base_url})'}")
    print("=" * 70)

    # Initialize client with appropriate transport
    if use_asgi or not base_url:
        transport = httpx.ASGITransport(app=app)
        client_kwargs = {"transport": transport, "base_url": "http://testserver"}
    else:
        client_kwargs = {"base_url": base_url}

    async with httpx.AsyncClient(**client_kwargs) as client:
        # Fire all requests simultaneously
        tasks = [
            send_single_redirect(client, target_path)
            for _ in range(concurrency)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, int) and r in (301, 302, 307)]
    errors = [r for r in results if isinstance(r, int) and r == 500]
    client_errors = [r for r in results if isinstance(r, int) and 400 <= r < 500]
    exceptions = [r for r in results if isinstance(r, Exception)]

    summary = {
        "concurrency": concurrency,
        "total_requests": len(results),
        "success_count": len(successes),
        "error_500_count": len(errors),
        "client_error_count": len(client_errors),
        "exception_count": len(exceptions),
        "raw_status_codes": [r if isinstance(r, int) else type(r).__name__ for r in results],
    }

    print("\n--- Repro Run Summary ---")
    print(f"Successes (301/302/307) : {len(successes)}")
    print(f"Server Errors (500)     : {len(errors)}")
    print(f"Client Errors (4xx)     : {len(client_errors)}")
    print(f"Exceptions / Network    : {len(exceptions)}")
    print(f"Status Code Breakdown   : {summary['raw_status_codes']}")

    if len(errors) > 0:
        print("\n[RESULT] BUG REPRODUCED: Intermittent HTTP 500 triggered under concurrent load.")
    else:
        print("\n[RESULT] No 500 errors observed in this run.")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Synthetic Reproduction Harness for Concurrency Bugs")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent requests (default: 10)")
    parser.add_argument("--code", type=str, default="test-popular-link", help="Short code to stress (default: test-popular-link)")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of live server (e.g. http://localhost:8000)")
    parser.add_argument("--asgi", action="store_true", default=True, help="Force ASGI in-process transport (default: True)")

    args = parser.parse_args()

    # Ensure synthetic test link exists in database
    ensure_synthetic_test_link(args.code)

    # Run reproduction
    asyncio.run(
        run_concurrent_repro(
            base_url=args.base_url,
            short_code=args.code,
            concurrency=args.concurrency,
            use_asgi=args.asgi if not args.base_url else False,
        )
    )


if __name__ == "__main__":
    main()
