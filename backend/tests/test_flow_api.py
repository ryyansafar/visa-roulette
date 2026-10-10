import pytest
from fastapi.testclient import TestClient

from visa_roulette import flow_api
from visa_roulette.api import create_app
from visa_roulette.handoff import decode_handoff
from visa_roulette.imu_sim import synth_throw

client = TestClient(create_app())

PROFILE = {"origin": "IND", "nationality": "IND", "age": 24, "gender": "male", "name": "arjun menon",
           "passport_type": "ordinary", "visas": [{"country": "ARE", "kind": "tourist"}]}
MRZ = ["P<INDMENON<<ARJUN<<<<<<<<<<<<<<<<<<<<<<<<<<<",
       "Z7654321<9IND0207142M3308154SPECIMEN<<<<<<22"]


def test_profile_is_validated_and_normalised():
    res = client.post("/api/profile", json=PROFILE)
    assert res.status_code == 200 and res.json()["name"] == "ARJUN MENON"


def test_bad_profile_is_a_422():
    assert client.post("/api/profile", json={**PROFILE, "nationality": "XXX"}).status_code == 422


def test_prefill_from_scanned_mrz_lines():
    res = client.post("/api/profile/prefill", json={"mrz_lines": MRZ})
    assert res.status_code == 200
    body = res.json()
    assert body["nationality"] == "IND" and body["gender"] == "male" and body["passport_type"] == "ordinary"
    assert isinstance(body["age"], int)


def test_prefill_rejects_a_garbled_mrz():
    res = client.post("/api/profile/prefill", json={"mrz_lines": ["X" * 44, "Y" * 44]})
    assert res.status_code == 422 and res.json()["detail"]["code"] == "bad_mrz"


def test_flick_throw():
    res = client.post("/api/throw/flick", json={"dx": 200, "dy": 0, "dt_ms": 120})
    assert res.status_code == 200
    assert res.json()["heading_deg"] == pytest.approx(90.0) and res.json()["source"] == "flick"


def test_switch_throw_and_its_validation():
    ok = client.post("/api/throw/switch", json={"heading_deg": 200, "power": 0.7})
    assert ok.status_code == 200 and ok.json()["source"] == "switch"
    bad = client.post("/api/throw/switch", json={"heading_deg": 400, "power": 0.7})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "bad_heading"


def test_imu_batch_throw():
    res = client.post("/api/throw/imu", json={"samples": synth_throw(8.0, 45.0, 0.0)})
    assert res.status_code == 200
    assert res.json()["speed_mps"] == pytest.approx(8.0, rel=0.1)


def test_imu_batch_with_no_throw_is_a_clear_error():
    res = client.post("/api/throw/imu", json={"samples": synth_throw(0.0, 45.0, 0.0)})
    assert res.status_code == 422 and res.json()["detail"]["code"] == "no_throw"


def test_imu_batch_size_is_bounded():
    res = client.post("/api/throw/imu", json={"samples": [[0.0, 0.0, 0.0, 9.8]] * 5001})
    assert res.status_code == 422


def test_landing_resolves_to_a_country():
    res = client.post("/api/landing", json={"origin": "IND", "heading_deg": 270, "distance_km": 2000})
    assert res.status_code == 200
    body = res.json()
    assert body["iso3"] and body["name"] and body["start"]["lat"] and "snapped" in body


def test_landing_with_a_passport_only_lands_where_there_is_a_rule():
    from visa_roulette.visa import reachable

    for heading in (0, 90, 180, 270):
        res = client.post("/api/landing", json={"origin": "IND", "heading_deg": heading, "distance_km": 9000, "nationality": "IND"})
        assert res.json()["iso3"] in reachable("IND")


def test_landing_unknown_origin_is_a_422():
    res = client.post("/api/landing", json={"origin": "XXX", "heading_deg": 0, "distance_km": 10})
    assert res.status_code == 422


def handoff_body(**kw):
    return {"profile": PROFILE, "landing_iso3": "ARE", "lat": 25.2, "lon": 55.3,
            "budget": 1500, "currency": "USD", "consent": True, **kw}


def test_handoff_returns_a_decodable_payload_a_matrix_and_a_phone_url():
    res = client.post("/api/handoff", json=handoff_body())
    assert res.status_code == 200
    body = res.json()
    assert decode_handoff(body["text"]).landing_iso3 == "ARE"
    assert len(body["matrix"]) == body["size"] == len(body["matrix"][0])
    assert "/phone.html#" in body["url"] and body["text"] not in body["url"]


def test_handoff_carries_the_rule_verdict_computed_by_the_server():
    body = client.post("/api/handoff", json=handoff_body(landing_iso3="BRA")).json()
    card = decode_handoff(body["text"])
    assert card.visa.status == "required" and card.visa.as_of and card.visa.source_url
    assert card.preflight is None
    assert "Passport valid for 6+ months" in card.needs and len(card.needs) <= 8


def test_handoff_keeps_the_preflight_summary_and_rejects_a_forged_verdict_shape():
    ok = client.post("/api/handoff", json=handoff_body(preflight={"verdict": "HELD", "readiness": 40}))
    assert decode_handoff(ok.json()["text"]).preflight.verdict == "HELD"
    bad = client.post("/api/handoff", json=handoff_body(preflight={"verdict": "FINE", "readiness": 400}))
    assert bad.status_code == 422


def test_handoff_url_swaps_localhost_for_the_lan_address(monkeypatch):
    monkeypatch.setattr(flow_api, "_lan_ip", lambda: "192.168.1.42")
    local = client.post("/api/handoff", json=handoff_body(), headers={"host": "localhost:8766"}).json()
    assert local["url"].startswith("http://192.168.1.42:8766/phone.html#") and "VR1." not in local["url"]
    remote = client.post("/api/handoff", json=handoff_body(), headers={"host": "booth.example:80"}).json()
    assert "192.168" not in remote["url"] and "booth.example" in remote["url"]


def test_handoff_without_consent_is_refused():
    res = client.post("/api/handoff", json=handoff_body(consent=False))
    assert res.status_code == 422 and res.json()["detail"]["code"] == "no_consent"


def test_esp32_stream_reaches_the_browser_as_a_throw_event():
    with client.websocket_connect("/ws/throw") as viewer:
        assert viewer.receive_json()["type"] == "hello"
        with client.websocket_connect("/ws/imu") as device:
            assert viewer.receive_json() == {"type": "device", "online": True}
            rows = synth_throw(8.0, 45.0, 0.0)
            for i in range(0, len(rows), 50):
                device.send_json({"samples": rows[i : i + 50]})
            event = viewer.receive_json()
        assert event["type"] == "throw" and event["speed_mps"] == pytest.approx(8.0, rel=0.1)
        assert viewer.receive_json() == {"type": "device", "online": False}


def test_weak_stream_throw_is_reported_as_rejected():
    with client.websocket_connect("/ws/throw") as viewer, client.websocket_connect("/ws/imu") as device:
        viewer.receive_json()
        viewer.receive_json()  # device online
        device.send_json({"samples": synth_throw(1.0, 45.0, 0.0, push_s=0.04)})
        event = viewer.receive_json()
    assert event["type"] == "rejected" and event["code"] == "too_weak"


def test_garbage_from_a_device_does_not_kill_the_hub():
    with client.websocket_connect("/ws/throw") as viewer, client.websocket_connect("/ws/imu") as device:
        viewer.receive_json()
        viewer.receive_json()
        device.send_json({"samples": "nope"})
        assert viewer.receive_json()["type"] == "device_error"
        rows = synth_throw(8.0, 45.0, 0.0)
        for i in range(0, len(rows), 50):  # small batches, as the ESP32 sends them
            device.send_json({"samples": rows[i : i + 50]})
        assert viewer.receive_json()["type"] == "throw"


def test_country_list_endpoint():
    body = client.get("/api/countries").json()
    india = next(c for c in body if c["iso3"] == "IND")
    assert india["name"] == "India" and 8 < india["lat"] < 35 and 68 < india["lon"] < 97
    assert len(body) > 150


def test_visa_requirement_endpoint():
    res = client.post("/api/visa/requirement", json={"nationality": "IND", "destination": "ARE", "visas": [{"country": "USA", "kind": "tourist"}]})
    body = res.json()
    assert res.status_code == 200 and body["status"] == "on_arrival" and body["unlocked_by"] == "USA" and body["verified"] is False


def test_visa_map_endpoint():
    res = client.post("/api/visa/map", json={"nationality": "IND", "visas": []})
    assert res.status_code == 200 and res.json()["BTN"] == "free"


def test_visa_endpoint_rejects_a_bad_country():
    assert client.post("/api/visa/requirement", json={"nationality": "IND", "destination": "XXX"}).status_code == 422


def _scan(matrix):
    import zxingcpp
    from PIL import Image

    scale, border = 6, 4
    size = (len(matrix) + 2 * border) * scale
    img = Image.new("L", (size, size), 255)
    px = img.load()
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                for dy in range(scale):
                    for dx in range(scale):
                        px[(x + border) * scale + dx, (y + border) * scale + dy] = 0
    return [r.text for r in zxingcpp.read_barcodes(img)]


def test_the_qr_opens_the_phone_page_when_scanned_by_a_plain_camera_app():
    body = client.post("/api/handoff", json=handoff_body()).json()
    assert _scan(body["matrix"]) == [body["url"]]
    assert body["url"].startswith("http")


def test_the_qr_stays_sparse_enough_for_a_phone_to_read_off_a_screen():
    body = client.post("/api/handoff", json=handoff_body(landing_iso3="BRA")).json()
    assert body["size"] <= 41, "a short link, not the whole card"
    assert len(body["url"]) < 90


def test_the_phone_fetches_the_card_by_the_short_id_in_the_link():
    body = client.post("/api/handoff", json=handoff_body()).json()
    card_id = body["url"].rsplit("#", 1)[1]
    fetched = client.get(f"/api/handoff/{card_id}")
    assert fetched.status_code == 200 and fetched.json() == {"text": body["text"]}


def test_an_unknown_or_malformed_card_id_is_a_clean_404():
    assert client.get("/api/handoff/nope-nope").status_code == 404
    assert client.get("/api/handoff/" + "x" * 80).status_code == 404


def test_old_cards_are_forgotten_so_memory_stays_bounded():
    first = client.post("/api/handoff", json=handoff_body()).json()["url"].rsplit("#", 1)[1]
    for _ in range(flow_api.MAX_CARDS + 1):
        client.post("/api/handoff", json=handoff_body())
    assert client.get(f"/api/handoff/{first}").status_code == 404
