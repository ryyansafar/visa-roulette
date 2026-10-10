import json
import random

import pytest
from fastapi.testclient import TestClient

from visa_roulette import flow_api
from visa_roulette.api import create_app
from visa_roulette.handoff import decode_handoff
from visa_roulette.souvenirs import DEFAULT_NICKNAME, DEFAULT_NOTE, Journal, Souvenir, clean

SEED = [
    {"origin": "GBR", "landing_iso3": "JPN", "nickname": "Oli", "note": "Egg sandwich."},
    {"origin": "USA", "landing_iso3": "EGY", "nickname": "Dana", "note": "Haggle."},
]
PROFILE = {"origin": "IND", "nationality": "IND", "age": 24, "gender": "male", "name": "arjun menon", "passport_type": "ordinary", "visas": []}


@pytest.fixture
def journal(tmp_path, monkeypatch):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps(SEED))
    made = Journal(tmp_path / "journal.jsonl", seed, random.Random(1))
    monkeypatch.setattr(flow_api, "journal", made)
    return made


def mine(**kw):
    return Souvenir(**{"origin": "IND", "landing_iso3": "ARE", "nickname": "Me", "note": "Nice.", **kw})


def test_clean_strips_control_characters_collapses_space_and_caps_length():
    assert clean("hi\x00\n\x07  there", 80, "x") == "hi there"
    assert clean("a" * 200, 80, "x") == "a" * 80
    assert clean("  \x00 ", 80, "fallback") == "fallback"
    assert clean(None, 80, "fallback") == "fallback"


def test_you_get_a_stranger_and_never_your_own_back(journal):
    first = journal.swap(mine())
    assert first.seeded is True
    assert journal.swap(mine()).nickname != "Me"


def test_your_souvenir_is_kept_once_and_the_next_visitor_can_receive_it(journal):
    journal.swap(mine())
    journal.swap(mine())
    assert len([s for s in journal.all() if not s.seeded]) == 1
    seen = {journal.swap(mine(origin="USA", landing_iso3="EGY", nickname=f"V{i}", note="n")).nickname for i in range(40)}
    assert "Me" in seen


def test_a_different_country_is_preferred(journal):
    for _ in range(10):
        assert journal.swap(mine(landing_iso3="JPN")).landing_iso3 == "EGY"


def test_an_empty_journal_hands_back_nothing(tmp_path):
    assert Journal(tmp_path / "j.jsonl", tmp_path / "none.json").swap(mine()) is None


def test_a_damaged_journal_line_is_skipped_not_fatal(journal):
    journal.path.write_text('not json\n{"origin":"FRA","landing_iso3":"ITA","nickname":"Z","note":"ok"}\n{"origin":"x"}\n')
    assert [s.nickname for s in journal.all() if not s.seeded] == ["Z"]


client = TestClient(create_app())


def body(**kw):
    return {"profile": PROFILE, "landing_iso3": "ARE", "lat": 25.2, "lon": 55.3, "budget": 1500, "currency": "USD", "consent": True, **kw}


def test_handoff_without_leave_has_no_swap_and_writes_nothing(journal):
    res = client.post("/api/handoff", json=body()).json()
    assert res["stranger"] is None and decode_handoff(res["text"]).stranger is None
    assert not journal.path.exists()


def test_handoff_with_leave_returns_a_stranger_with_a_visa_line_for_you(journal):
    res = client.post("/api/handoff", json=body(leave={"nickname": "Arjun", "note": "Chai at the creek."})).json()
    stranger = res["stranger"]
    assert stranger["landing_iso3"] in {"JPN", "EGY"} and stranger["seeded"] is True
    assert stranger["for_you_status"] and stranger["for_you_label"]
    assert decode_handoff(res["text"]).stranger.nickname == stranger["nickname"]
    assert json.loads(journal.path.read_text().splitlines()[0])["note"] == "Chai at the creek."


def test_the_note_is_sanitised_and_blank_falls_back_to_a_default(journal):
    client.post("/api/handoff", json=body(leave={"nickname": "\x00\x07", "note": "line\none\x1b" + "z" * 300}))
    saved = json.loads(journal.path.read_text().splitlines()[0])
    assert saved["nickname"] == DEFAULT_NICKNAME and len(saved["note"]) <= 80 and "\n" not in saved["note"]
    client.post("/api/handoff", json=body(leave={}))
    assert json.loads(journal.path.read_text().splitlines()[1])["note"] == DEFAULT_NOTE


def test_a_forged_stranger_in_the_request_is_ignored(journal):
    forged = {"origin": "FRA", "landing_iso3": "ITA", "nickname": "Evil", "note": "pwn"}
    res = client.post("/api/handoff", json=body(stranger=forged)).json()
    assert res["stranger"] is None and decode_handoff(res["text"]).stranger is None


def test_an_oversized_leave_is_refused(journal):
    assert client.post("/api/handoff", json=body(leave={"note": "x" * 501})).status_code == 422
