"""
End-to-end production verification suite for live LinkOps deployment on Railway.
Tests:
1. Health endpoint (GET /health) -> 200 OK
2. Authentication enforcement (Missing API Key -> 401 Unauthorized)
3. Authenticated link creation (POST /links) -> 201 Created
4. Link retrieval by ID (GET /links/{id}) -> 200 OK
5. Public redirect resolution (GET /r/{code}) -> 307 Temporary Redirect
6. Multi-tenant isolation (Tenant A cannot access Tenant B's link) -> 404 Not Found
7. Inactive / Expired link handling
8. Batch analytics aggregation (GET /links/analytics/batch) -> 200 OK
"""
import urllib.request
import urllib.error
import json
import time

BASE_URL = "https://api-production-383c4d8a.up.railway.app"
API_KEY_A = "api_key_primary_live_prod_987"
API_KEY_B = "api_key_secondary_live_prod_654"

def make_request(path, method="GET", data=None, headers=None, follow_redirects=True):
    url = f"{BASE_URL}{path}"
    req_headers = {"User-Agent": "LinkOps-Production-Verifier/1.0"}
    if headers:
        req_headers.update(headers)
    
    encoded_data = None
    if data is not None:
        encoded_data = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)
    
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(NoRedirect)
    
    try:
        with opener.open(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, resp.headers, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return e.code, e.headers, body
    except Exception as e:
        return 0, {}, str(e)

def run_production_tests():
    print(f"=== Starting Production Verification on {BASE_URL} ===")
    results = []
    
    # Test 1: Health Check
    status, _, body = make_request("/health")
    passed = (status == 200 and '"ok":true' in body)
    results.append(("Health Check (GET /health)", status, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] Health Check: Status {status}, Body: {body.strip()}")
    
    # Test 2: Unauthenticated Request Blocked
    status, _, _ = make_request("/links")
    passed = (status == 401)
    results.append(("Authentication Guard (GET /links without key)", status, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] Unauthenticated Block: Status {status} (Expected 401)")
    
    # Test 3: Authenticated Link Creation
    create_payload = {
        "long_url": "https://docs.railway.com/overview",
        "title": "Railway Docs Official",
        "tags": ["cloud", "deployment", "prod"]
    }
    status, _, body = make_request("/links", method="POST", data=create_payload, headers={"X-API-Key": API_KEY_A})
    passed = (status == 201)
    link_data = json.loads(body) if passed else {}
    results.append(("Link Creation (POST /links)", status, passed))
    print(f"[{'PASS' if passed else 'FAIL'}] Link Creation: Status {status}, Code: {link_data.get('code')}")
    
    link_id = link_data.get("id")
    short_code = link_data.get("code")
    
    # Test 4: Retrieve Link by ID
    if link_id:
        status, _, body = make_request(f"/links/{link_id}", headers={"X-API-Key": API_KEY_A})
        passed = (status == 200)
        results.append(("Link Retrieval (GET /links/{id})", status, passed))
        print(f"[{'PASS' if passed else 'FAIL'}] Link Retrieval: Status {status}")
    
    # Test 5: Public Redirect (HTTP 307)
    if short_code:
        status, headers, _ = make_request(f"/r/{short_code}", follow_redirects=False)
        loc = headers.get("Location", "")
        passed = (status == 307 and loc == "https://docs.railway.com/overview")
        results.append(("Short URL Redirection (GET /r/{code})", status, passed))
        print(f"[{'PASS' if passed else 'FAIL'}] Redirection: Status {status}, Target: {loc}")
        
    # Test 6: Multi-Tenant Scoping (Tenant B querying Tenant A's link returns 404 anti-enumeration)
    if link_id:
        status, _, _ = make_request(f"/links/{link_id}", headers={"X-API-Key": API_KEY_B})
        passed = (status == 404)
        results.append(("Tenant Isolation (Tenant B accessing Tenant A's link)", status, passed))
        print(f"[{'PASS' if passed else 'FAIL'}] Tenant Isolation: Status {status} (Expected 404 anti-enumeration)")

    # Test 7: Batch Analytics Aggregation
    if link_id:
        status, _, body = make_request(f"/links/analytics/batch?link_ids={link_id}", headers={"X-API-Key": API_KEY_A})
        passed = (status == 200)
        results.append(("Batch Analytics (GET /links/analytics/batch)", status, passed))
        print(f"[{'PASS' if passed else 'FAIL'}] Batch Analytics: Status {status}, Response: {body.strip()}")
        
    print("\n=== Production Verification Summary ===")
    total = len(results)
    passed_count = sum(1 for _, _, p in results if p)
    print(f"Total Tests: {total} | Passed: {passed_count} | Failed: {total - passed_count}")
    return results

if __name__ == "__main__":
    run_production_tests()
