import pytest
from fastapi.testclient import TestClient

from visa_roulette.api import create_app
from visa_roulette.duel import duel, strength
from visa_roulette.profile import VisaHeld

client = TestClient(create_app())


def test_strength_orders_the_easier_entry_first():
    order = ["free", "on_arrival", "evisa", "required"]
    assert [strength(s) for s in order] == sorted(strength(s) for s in order)
    assert strength("home") == strength("held") == strength("free")


def test_unknown_has_no_strength_so_it_can_never_win():
    assert strength("unknown") is None


def test_the_easier_passport_wins_the_duel():
    result = duel("IND", "GBR", "THA")
    assert result["winner"] in ("a", "b")
    won = result[result["winner"]]["verdict"]["status"]
    lost = result["b" if result["winner"] == "a" else "a"]["verdict"]["status"]
    assert strength(won) < strength(lost)


def test_equal_verdicts_are_a_draw():
    result = duel("GBR", "GBR", "THA")
    assert result["winner"] is None


def test_a_missing_rule_means_no_winner():
    result = duel("IND", "ZZZ", "THA")
    assert result["winner"] is None and result["b"]["verdict"]["status"] == "unknown"


def test_each_side_carries_its_own_needs_and_source():
    result = duel("IND", "GBR", "THA")
    for side in ("a", "b"):
        assert result[side]["verdict"]["source_url"]
        assert result[side]["needs"]["items"] is not None
    assert result["destination"] == "THA"


def test_a_held_visa_changes_that_sides_verdict_only():
    held = [VisaHeld(country="GEO", kind="tourist")]
    result = duel("IND", "GBR", "GEO", a_visas=held)
    assert result["a"]["verdict"]["status"] == "held"
    assert result["b"]["verdict"]["status"] == duel("IND", "GBR", "GEO")["b"]["verdict"]["status"]


def test_duel_endpoint_returns_both_verdicts():
    body = {"destination": "THA", "a": {"nationality": "IND"}, "b": {"nationality": "GBR"}}
    out = client.post("/api/duel", json=body)
    assert out.status_code == 200
    data = out.json()
    assert data["a"]["nationality"] == "IND" and data["b"]["nationality"] == "GBR"
    assert "winner" in data and data["destination"] == "THA"


def test_duel_endpoint_rejects_an_unknown_destination():
    body = {"destination": "ZZZ", "a": {"nationality": "IND"}, "b": {"nationality": "GBR"}}
    assert client.post("/api/duel", json=body).status_code == 422


def test_duel_endpoint_rejects_a_bad_passport_code():
    body = {"destination": "THA", "a": {"nationality": "india"}, "b": {"nationality": "GBR"}}
    assert client.post("/api/duel", json=body).status_code == 422


@pytest.mark.parametrize("missing", ["a", "b", "destination"])
def test_duel_endpoint_needs_both_passports_and_a_destination(missing):
    body = {"destination": "THA", "a": {"nationality": "IND"}, "b": {"nationality": "GBR"}}
    body.pop(missing)
    assert client.post("/api/duel", json=body).status_code == 422
