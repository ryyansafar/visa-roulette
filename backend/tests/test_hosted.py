"""Hosted (Vercel) mode: no hardware, no heavy libraries, and the sample travellers still work."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from visa_roulette import hosted
from visa_roulette.api import create_app
from visa_roulette.handoff import decode_handoff

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "fixtures" / "manifest.json").read_text())
HEAVY = ("cv2", "zxingcpp", "faster_whisper")  # Pillow is light; qrcode imports it only when it happens to be installed


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(hosted, "can_read_passport", lambda: False)
    monkeypatch.setattr(hosted, "can_read_boarding", lambda: False)
    return TestClient(create_app(hosted_mode=True))


def image(key: str, name: str) -> bytes:
    return (ROOT / "fixtures" / key / f"{name}.png").read_bytes()


def test_health_says_it_is_hosted(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["hosted"] is True


def test_hosted_app_does_not_serve_static_files(client):
    assert client.get("/").status_code == 404


@pytest.mark.parametrize("person", MANIFEST, ids=lambda p: p["key"])
def test_sample_passport_and_boarding_pass_are_answered_from_the_manifest(client, person):
    passport = client.post("/api/scan/passport", content=image(person["key"], "passport")).json()
    assert passport["mrz"]["lines"] == person["mrz"] and passport["mrz"]["all_checks_pass"] and passport["method"] == "fixture"
    boarding = client.post("/api/scan/boarding-pass", content=image(person["key"], "boarding_pass")).json()
    assert boarding["raw"] == person["bcbp"]


def test_any_other_image_is_a_clean_503(client):
    for path in ("/api/scan/passport", "/api/scan/boarding-pass"):
        reply = client.post(path, content=b"not a sample image")
        assert reply.status_code == 503
        assert reply.json()["detail"]["code"] == "unavailable_on_hosted"


def test_hosted_checklist_runs_from_the_sample_scan(client):
    person = MANIFEST[0]
    mrz = client.post("/api/scan/passport", content=image(person["key"], "passport")).json()["mrz"]["lines"]
    boarding = client.post("/api/scan/boarding-pass", content=image(person["key"], "boarding_pass")).json()["raw"]
    reply = client.post("/api/checklist", json={"mrz_lines": mrz, "boarding_pass": boarding, "travel_date": "2026-10-11"})
    assert reply.status_code == 200 and reply.json()["verdict"] in {"CLEARED", "REVIEW", "HELD"}


def test_hosted_handoff_link_carries_the_whole_card_and_uses_the_forwarded_host(client):
    body = {
        "profile": {"origin": "IND", "nationality": "IND", "age": 30, "visas": []},
        "landing_iso3": "THA", "lat": 15.0, "lon": 101.0, "budget": 500, "currency": "USD", "consent": True,
    }
    reply = client.post("/api/handoff", json=body, headers={"x-forwarded-host": "visa-roulette.vercel.app", "x-forwarded-proto": "https"})
    assert reply.status_code == 200, reply.text
    url = reply.json()["url"]
    assert url.startswith("https://visa-roulette.vercel.app/phone.html#VR1.")
    assert decode_handoff(url.split("#", 1)[1]).landing_iso3 == "THA"


def test_the_function_entrypoint_imports_without_the_heavy_modules():
    code = (
        "import sys, importlib.util\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "spec = importlib.util.spec_from_file_location('api_index', 'api/index.py')\n"
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
        f"loaded = [m for m in {HEAVY!r} if m in sys.modules]\n"
        "assert not loaded, loaded\n"
        "assert mod.app.state.hosted is True\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
