from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")


def get(path: str):
    request = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"detail": body}


def main() -> int:
    checks = [
        ("health", "/api/health"),
        ("metadata", "/api/meta"),
        ("routes", "/api/routes?limit=5"),
        ("stops", "/api/stops?q=railway&limit=80"),
        ("stop search 80-row regression", "/api/stops/search?q=railway&limit=80"),
        ("crowding overview", "/api/crowding/overview"),
        ("crowding trend", "/api/crowding/trends?day_type=weekday"),
        ("data quality", "/api/data-quality"),
        ("live feed status", "/api/live-vehicles"),
    ]
    failed = False
    for label, path in checks:
        try:
            status, payload = get(path)
            ok = status == 200
            print(f"{'PASS' if ok else 'FAIL'} {label}: HTTP {status}")
            if label == "health":
                print("  database_ready:", payload.get("database_ready"))
                print("  live_feed_configured:", payload.get("live_feed_configured"))
            if not ok:
                print("  detail:", payload.get("detail"))
                failed = True
        except Exception as exc:
            print(f"FAIL {label}: {exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
