import pytest
from fastapi.testclient import TestClient
from visa_roulette import officer_flow, operator
from visa_roulette.api import create_app

client = TestClient(create_app())
BODY = {"nationality": "IND", "destination": "ARE", "visas": []}


@pytest.fixture(autouse=True)
def _offline_model(monkeypatch):
    officer_flow.reset()
    monkeypatch.setattr(operator, "ollama_chat", lambda messages, timeout=0: (_ for _ in ()).throw(ConnectionError("off")))


def test_start_then_turn_walks_to_the_stamp():
    first = client.post("/api/officer/start", json=BODY).json()
    assert first["stage"] == "purpose" and first["persona"]["title"]
    last = first
    for said in ["tourism", "five days", "a hotel", "yes a ticket", "papers here", "thanks"]:
        if last["done"]:
            break
        last = client.post("/api/officer/turn", json={"session_id": first["session_id"], "said": said}).json()
    assert last["done"] and last["stamp"]["as_of"] in last["say"]
    assert client.post("/api/officer/turn", json={"session_id": first["session_id"], "said": "again"}).status_code == 404


def test_unknown_session_is_a_404():
    assert client.post("/api/officer/turn", json={"session_id": "nope", "said": "hi"}).status_code == 404


def test_unknown_country_is_a_422():
    assert client.post("/api/officer/start", json={**BODY, "destination": "ZZZ"}).status_code == 422


def test_overlong_speech_is_rejected():
    first = client.post("/api/officer/start", json=BODY).json()
    res = client.post("/api/officer/turn", json={"session_id": first["session_id"], "said": "a" * 2001})
    assert res.status_code == 422
