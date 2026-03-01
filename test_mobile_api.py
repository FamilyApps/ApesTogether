"""
Mobile API Test Suite
Tests all mobile API endpoints to catch 500 errors and broken responses before they hit production.
Run: python test_mobile_api.py [--base-url https://apestogether.ai]
"""
import requests
import sys
import json
import time

BASE_URL = "https://apestogether.ai/api/mobile"
RESULTS = {"passed": 0, "failed": 0, "warnings": 0, "tests": []}


def test(name, method, endpoint, expected_status=None, body=None, headers=None, authenticated=False, token=None):
    """Run a single API test"""
    url = f"{BASE_URL}{endpoint}"
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if authenticated and token:
        hdrs["Authorization"] = f"Bearer {token}"

    try:
        start = time.time()
        if method == "GET":
            resp = requests.get(url, headers=hdrs, timeout=15)
        elif method == "POST":
            resp = requests.post(url, json=body or {}, headers=hdrs, timeout=15)
        elif method == "PUT":
            resp = requests.put(url, json=body or {}, headers=hdrs, timeout=15)
        elif method == "DELETE":
            resp = requests.delete(url, headers=hdrs, timeout=15)
        else:
            raise ValueError(f"Unknown method: {method}")
        elapsed = time.time() - start

        # Determine pass/fail
        status_ok = True
        if expected_status:
            if isinstance(expected_status, list):
                status_ok = resp.status_code in expected_status
            else:
                status_ok = resp.status_code == expected_status
        else:
            # No 500s allowed
            status_ok = resp.status_code != 500

        # Check for timeout (Cloudflare 524)
        if resp.status_code == 524:
            status_ok = False

        result = {
            "name": name,
            "url": url,
            "status": resp.status_code,
            "elapsed": round(elapsed, 2),
            "passed": status_ok,
        }

        try:
            result["body_preview"] = json.dumps(resp.json())[:200]
        except Exception:
            result["body_preview"] = resp.text[:200]

        RESULTS["tests"].append(result)

        if status_ok:
            RESULTS["passed"] += 1
            icon = "✅"
        else:
            RESULTS["failed"] += 1
            icon = "❌"

        print(f"  {icon} {name} — {resp.status_code} ({elapsed:.2f}s)")
        if not status_ok:
            print(f"     Expected: {expected_status}, Got: {resp.status_code}")
            print(f"     Body: {result['body_preview']}")

        return resp

    except requests.Timeout:
        RESULTS["failed"] += 1
        RESULTS["tests"].append({"name": name, "url": url, "status": "TIMEOUT", "passed": False})
        print(f"  ❌ {name} — TIMEOUT (>15s)")
        return None
    except Exception as e:
        RESULTS["failed"] += 1
        RESULTS["tests"].append({"name": name, "url": url, "status": str(e), "passed": False})
        print(f"  ❌ {name} — ERROR: {e}")
        return None


def run_tests():
    print("=" * 60)
    print("MOBILE API TEST SUITE")
    print(f"Base URL: {BASE_URL}")
    print("=" * 60)

    # ── Health ──
    print("\n📋 Health & Connectivity")
    test("Health check", "GET", "/../health", expected_status=200)

    # ── Auth (unauthenticated) ──
    print("\n🔐 Auth Endpoints (unauthenticated)")
    test("Auth token - missing body", "POST", "/auth/token", expected_status=[400, 401, 422])
    test("Auth user - no token", "GET", "/auth/user", expected_status=401)
    test("Auth refresh - no token", "POST", "/auth/refresh", expected_status=401)

    # ── Leaderboard (public) ──
    print("\n🏆 Leaderboard Endpoints")
    test("Leaderboard - default", "GET", "/leaderboard", expected_status=200)
    test("Leaderboard - 1D period", "GET", "/leaderboard?period=1D&category=all", expected_status=200)
    test("Leaderboard - 1M period", "GET", "/leaderboard?period=1M&category=all", expected_status=200)
    test("Leaderboard - YTD period", "GET", "/leaderboard?period=YTD&category=all", expected_status=200)
    test("Leaderboard - large_cap filter", "GET", "/leaderboard?period=7D&category=large_cap", expected_status=200)
    test("Leaderboard - small_cap filter", "GET", "/leaderboard?period=7D&category=small_cap", expected_status=200)

    # ── Portfolio (authenticated required) ──
    print("\n📊 Portfolio Endpoints")
    test("Portfolio - no auth", "GET", "/portfolio/test-slug", expected_status=401)

    # ── Subscriptions (authenticated required) ──
    print("\n🔔 Subscription Endpoints")
    test("Subscriptions - no auth", "GET", "/subscriptions", expected_status=401)

    # ── Stocks (authenticated required) ──
    print("\n📈 Stock Endpoints")
    test("Add stocks - no auth", "POST", "/portfolio/stocks", expected_status=401, body={"stocks": []})

    # ── Device Registration ──
    print("\n📱 Device Registration")
    test("Register device - no auth", "POST", "/device/register", expected_status=401, body={"token": "test"})

    # ── Notification Settings ──
    print("\n🔔 Notification Settings")
    test("Update notifications - no auth", "PUT", "/notifications/settings", expected_status=401)

    # ── Account ──
    print("\n👤 Account Management")
    test("Delete account - no auth", "DELETE", "/auth/account", expected_status=401)

    # ── Summary ──
    print("\n" + "=" * 60)
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f"RESULTS: {RESULTS['passed']}/{total} passed, {RESULTS['failed']} failed")
    if RESULTS["failed"] == 0:
        print("🎉 ALL TESTS PASSED")
    else:
        print("⚠️  SOME TESTS FAILED — review above")
    print("=" * 60)

    return RESULTS["failed"] == 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--base-url":
        BASE_URL = sys.argv[2] + "/api/mobile"
    success = run_tests()
    sys.exit(0 if success else 1)
