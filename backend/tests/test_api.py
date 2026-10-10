import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from visa_roulette.api import create_app

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "fixtures" / "manifest.json").read_text())
BY_KEY = {p["key"]: p for p in MANIFEST}
KEYS = list(BY_KEY)
client = TestClient(create_app())
needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")


def prop(key: str, name: str) -> Image.Image:
    return Image.open(ROOT / "fixtures" / key / f"{name}.png").convert("RGB")


def encode(img: Image.Image, fmt: str = "PNG", **opts) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **opts)
    return buf.getvalue()


def degrade(img: Image.Image, scale: float, quality: int) -> bytes:
    small = img.resize((int(img.width * scale), int(img.height * scale)))
    return encode(small, "JPEG", quality=quality)


def post_image(path: str, data: bytes, **params):
    return client.post(path, content=data, headers={"content-type": "image/png"}, params=params)


# --- health ---------------------------------------------------------------

def test_health_reports_offline_capabilities():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(body["capabilities"]) >= {"tesseract", "opencv", "zxing"}
    assert body["capabilities"]["zxing"] is True


# --- boarding pass --------------------------------------------------------

@pytest.mark.parametrize("key", KEYS)
def test_boarding_pass_scan_returns_the_exact_barcode(key):
    res = post_image("/api/scan/boarding-pass", encode(prop(key, "boarding_pass")), year=2026)
    assert res.status_code == 200
    body = res.json()
    assert body["raw"] == BY_KEY[key]["bcbp"]
    assert body["boarding_pass"]["destination"] == "DXB"
    assert body["boarding_pass"]["flight_date"] == "2026-10-11"


def test_boarding_pass_survives_downscale_and_jpeg():
    res = post_image("/api/scan/boarding-pass", degrade(prop("arjun", "boarding_pass"), 0.6, 55), year=2026)
    assert res.status_code == 200
    assert res.json()["raw"] == BY_KEY["arjun"]["bcbp"]


def test_boarding_pass_scan_without_a_barcode_is_a_clear_error():
    blank = encode(Image.new("RGB", (800, 600), "white"))
    res = post_image("/api/scan/boarding-pass", blank)
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "no_barcode"


# --- passport -------------------------------------------------------------

@needs_tesseract
@pytest.mark.parametrize("key", KEYS)
def test_passport_scan_reads_the_mrz(key):
    res = post_image("/api/scan/passport", encode(prop(key, "passport")))
    assert res.status_code == 200
    mrz = res.json()["mrz"]
    assert mrz["lines"] == BY_KEY[key]["mrz"]
    assert mrz["all_checks_pass"] is True


@needs_tesseract
def test_passport_scan_survives_downscale_and_jpeg():
    res = post_image("/api/scan/passport", degrade(prop("lakshmi", "passport"), 0.7, 50))
    assert res.status_code == 200
    assert res.json()["mrz"]["all_checks_pass"] is True


@needs_tesseract
def test_passport_scan_finds_the_mrz_mid_frame():
    canvas = Image.new("RGB", (1400, 2000), (120, 124, 130))
    canvas.paste(prop("shafeeq", "passport"), (150, 100))
    res = post_image("/api/scan/passport", encode(canvas))
    assert res.status_code == 200
    assert res.json()["mrz"]["lines"] == BY_KEY["shafeeq"]["mrz"]


@needs_tesseract
def test_passport_scan_without_an_mrz_is_a_clear_error():
    res = post_image("/api/scan/passport", encode(Image.new("RGB", (900, 600), "white")))
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "no_mrz"


# --- input safety ---------------------------------------------------------

def test_non_image_bytes_are_rejected():
    res = post_image("/api/scan/passport", b"hello, not an image")
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_image"


def test_oversized_bodies_are_rejected():
    res = post_image("/api/scan/passport", b"x" * (11 * 1024 * 1024))
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "too_large"


def test_path_traversal_through_static_mounts_is_blocked():
    assert client.get("/fixtures/../README.md").status_code in (400, 404)
    assert client.get("/fixtures/%2e%2e/README.md").status_code in (400, 404)


# --- checklist ------------------------------------------------------------

def checklist_payload(key: str, **overrides) -> dict:
    p = BY_KEY[key]
    payload = {
        "mrz_lines": p["mrz"],
        "boarding_pass": p["bcbp"],
        "return_ticket_name": p["booking_name"],
        "hotel_name": p["booking_name"],
        "bag": p["bag"],
        "travel_date": "2026-10-11",
        "ticked": [],
    }
    return {**payload, **overrides}


@pytest.mark.parametrize("key", KEYS)
def test_checklist_verdict_matches_the_manifest(key):
    res = client.post("/api/checklist", json=checklist_payload(key))
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == BY_KEY[key]["expected"]
    assert all({"rule_id", "status", "detail", "source_url", "as_of", "verified"} <= set(i) for i in body["items"])


def test_checklist_respects_ticked_items():
    body = client.post("/api/checklist", json=checklist_payload("arjun", ticked=["R-MAN-INSURANCE"])).json()
    status = {i["rule_id"]: i["status"] for i in body["items"]}
    assert status["R-MAN-INSURANCE"] == "pass"
    assert status["R-MAN-FUNDS"] == "manual"


@pytest.mark.parametrize(
    "override",
    [
        {"mrz_lines": ["short", "lines"]},
        {"travel_date": "next tuesday"},
        {"bag": ["item"] * 51},
        {"boarding_pass": "nope"},
        {"ticked": ["../../etc/passwd"]},
    ],
)
def test_checklist_rejects_bad_payloads(override):
    res = client.post("/api/checklist", json=checklist_payload("arjun", **override))
    assert res.status_code == 422


# --- demo data ------------------------------------------------------------

def test_demo_personas_expose_image_urls_that_resolve():
    personas = client.get("/api/demo/personas").json()
    assert {p["key"] for p in personas} == set(KEYS)
    url = personas[0]["images"]["passport"]
    res = client.get(url)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
