import json
import random

import pytest
from fastapi.testclient import TestClient

from visa_roulette import flow_api
from visa_roulette.api import create_app
from visa_roulette.souvenirs import Journal, Souvenir
from visa_roulette.visa import requirement
from visa_roulette.wall import build_wall

client = TestClient(create_app())
PROFILE = {"origin": "IND", "nationality": "IND", "age": 24, "gender": "male", "name": "arjun menon", "passport_type": "ordinary", "visas": []}


def row(origin="IND", landing="GEO", nickname="Arjun", status="free", seeded=False, nationality=None):
    return Souvenir(origin=origin, landing_iso3=landing, nickname=nickname, note="n", status=status, nationality=nationality, seeded=seeded)


def test_an_empty_night_has_a_wall_with_zeroed_stats():
    wall = build_wall([])
    assert wall["stats"] == {"total": 0, "visa_free_rate": 0.0, "most_landed": None, "luckiest_passport": None}
    assert wall["pins"] == [] and wall["ticker"] == []


def test_pins_and_ticker_list_every_landing_newest_first():
    wall = build_wall([row(nickname="First"), row(nickname="Second", landing="JPN", status="evisa")])
    assert [p["iso3"] for p in wall["pins"]] == ["GEO", "JPN"]
    assert [t["nickname"] for t in wall["ticker"]] == ["Second", "First"]
    assert wall["ticker"][0]["label"] == "E-visa needed, apply online first"


def test_ticker_is_capped():
    assert len(build_wall([row(nickname=f"V{i}") for i in range(40)], ticker_size=12)["ticker"]) == 12


def test_stats_count_the_most_landed_country_and_the_visa_free_rate():
    wall = build_wall([row(landing="GEO"), row(landing="GEO", nickname="B"), row(landing="JPN", status="required", nickname="C"), row(landing="THA", status="free", nickname="D")])
    stats = wall["stats"]
    assert stats["total"] == 4 and stats["most_landed"] == {"iso3": "GEO", "count": 2}
    assert stats["visa_free_rate"] == 0.75


def test_passport_of_the_night_is_the_nationality_with_the_best_visa_free_rate():
    wall = build_wall([
        row(nationality="IND", status="required"), row(nationality="IND", status="free", nickname="B"),
        row(nationality="GBR", status="free", nickname="C"), row(nationality="GBR", status="free", nickname="D"),
    ])
    assert wall["stats"]["luckiest_passport"] == {"nationality": "GBR", "rate": 1.0, "landings": 2}


def test_seeded_rows_without_a_stored_status_are_judged_by_the_rules():
    wall = build_wall([Souvenir(origin="IND", landing_iso3="BTN", nickname="Anu", note="n", seeded=True)])
    assert wall["ticker"][0]["status"] == "free" and wall["ticker"][0]["seeded"] is True


@pytest.fixture
def journal(tmp_path, monkeypatch):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps([{"origin": "GBR", "landing_iso3": "JPN", "nickname": "Oli", "note": "Egg."}]))
    made = Journal(tmp_path / "journal.jsonl", seed, random.Random(1))
    monkeypatch.setattr(flow_api, "journal", made)
    return made


def handoff_body(**kw):
    return {"profile": PROFILE, "landing_iso3": "ARE", "lat": 25.2, "lon": 55.3, "budget": 1500, "currency": "USD", "consent": True, **kw}


def test_wall_endpoint_shows_seeded_travellers_before_anyone_lands(journal):
    body = client.get("/api/wall").json()
    assert body["stats"]["total"] == 1 and body["ticker"][0]["seeded"] is True


def test_a_finished_visitor_lands_on_the_wall_with_the_server_computed_verdict(journal):
    client.post("/api/handoff", json=handoff_body(leave={"nickname": "Arjun", "note": "Hi"}))
    body = client.get("/api/wall").json()
    mine = body["ticker"][0]
    assert mine["nickname"] == "Arjun" and mine["iso3"] == "ARE" and mine["origin"] == "IND"
    assert mine["status"] == requirement("IND", "ARE").status
    assert mine["seeded"] is False and body["stats"]["total"] == 2


def test_a_visitor_who_does_not_opt_in_is_not_on_the_wall(journal):
    client.post("/api/handoff", json=handoff_body())
    assert client.get("/api/wall").json()["stats"]["total"] == 1


def test_the_stranger_chip_does_not_carry_the_other_travellers_nationality_or_status(journal):
    client.post("/api/handoff", json=handoff_body(leave={"nickname": "Arjun", "note": "Hi"}))
    chip = client.post("/api/handoff", json=handoff_body(leave={"nickname": "Lakshmi", "note": "Yo"})).json()["stranger"]
    assert chip["nationality"] is None and chip["status"] is None
