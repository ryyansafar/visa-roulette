#!/usr/bin/env python3
"""Smoke test for a hosted Visa Roulette: python3 scripts/smoke_hosted.py https://your-app.vercel.app

Pass the origin of the static site and, when the API runs elsewhere (local simulation), a second origin for /api.
Uses only the standard library. Exits non-zero if any check fails.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ["/", "/phone.html", "/wall.html", "/journey.html", "/js/main.js", "/styles/tokens.css", "/vendor/three.module.min.js",
          "/assets/logo.svg", "/assets/globe/countries.geojson", "/assets/fonts/space-grotesk-latin-700-normal.woff2",
          "/assets/places/THA-1.jpg", "/fixtures/arjun/passport.png"]
BODY = {"nationality": "IND", "destination": "THA", "visas": []}
JSON_POSTS = [
    ("/api/profile", {"origin": "IND", "nationality": "IND", "age": 30}),
    ("/api/visa/map", {"nationality": "IND", "visas": []}),
    ("/api/throw/flick", {"dx": 120, "dy": -300, "dt_ms": 80}),
    ("/api/landing", {"origin": "IND", "heading_deg": 90, "distance_km": 3000, "nationality": "IND"}),
    ("/api/visa/requirement", BODY),
    ("/api/duel", {"destination": "JPN", "a": {"nationality": "IND"}, "b": {"nationality": "DEU"}}),
    ("/api/pick/THA/answer", {"choice": "passport"}),
    ("/api/operator/ask", {**BODY, "question": "Do I need a visa?"}),
    ("/api/officer/start", {"nationality": "IND", "destination": "THA"}),
]
JSON_GETS = ["/api/countries", "/api/demo/personas", "/api/pick/THA", "/api/wall", "/api/destination/THA"]


def call(url: str, data: bytes | None = None, content_type: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers={"content-type": content_type} if content_type else {})
    try:
        with urllib.request.urlopen(request, timeout=30) as reply:
            return reply.status, reply.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def main(static: str, api: str) -> int:
    failures = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(("ok    " if ok else "FAIL  ") + name + (f"  {detail}" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    for path in STATIC:
        status, _ = call(static + path)
        check(f"GET  {path}", status == 200, str(status))
    status, body = call(api + "/api/health")
    health = json.loads(body) if status == 200 else {}
    check("GET  /api/health", status == 200 and health.get("status") == "ok", str(status))
    for path in JSON_GETS:
        status, _ = call(api + path)
        check(f"GET  {path}", status == 200, str(status))
    for path, payload in JSON_POSTS:
        status, _ = call(api + path, json.dumps(payload).encode(), "application/json")
        check(f"POST {path}", status == 200, str(status))

    person = json.loads((ROOT / "fixtures" / "manifest.json").read_text())[0]["key"]
    passport = (ROOT / "fixtures" / person / "passport.png").read_bytes()
    boarding = (ROOT / "fixtures" / person / "boarding_pass.png").read_bytes()
    status, body = call(api + "/api/scan/passport", passport, "image/png")
    mrz = json.loads(body).get("mrz", {}).get("lines") if status == 200 else None
    check("POST /api/scan/passport (sample traveller)", bool(mrz), str(status))
    status, body = call(api + "/api/scan/boarding-pass", boarding, "image/png")
    raw = json.loads(body).get("raw") if status == 200 else None
    check("POST /api/scan/boarding-pass (sample traveller)", bool(raw), str(status))
    if mrz and raw:
        payload = {"mrz_lines": mrz, "boarding_pass": raw, "travel_date": "2026-10-11"}
        status, _ = call(api + "/api/checklist", json.dumps(payload).encode(), "application/json")
        check("POST /api/checklist", status == 200, str(status))
    if health.get("hosted"):
        status, body = call(api + "/api/scan/passport", b"not a sample image", "image/png")
        code = (json.loads(body).get("detail") or {}).get("code") if status == 503 else None
        check("hosted: unknown image is a clean 503", code == "unavailable_on_hosted", f"{status} {code}")
    print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    origin = sys.argv[1].rstrip("/")
    sys.exit(main(origin, (sys.argv[2] if len(sys.argv) == 3 else origin).rstrip("/")))
