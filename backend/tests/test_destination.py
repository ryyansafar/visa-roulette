import json
from pathlib import Path

from fastapi.testclient import TestClient

from visa_roulette import destination
from visa_roulette.api import create_app

client = TestClient(create_app())
FIXTURE = Path(__file__).resolve().parents[2] / "web" / "fixtures" / "destination.sample.json"


def test_a_curated_country_returns_highlights_season_tip_and_source():
    body = client.get("/api/destination/ARE").json()
    assert body["name"] and body["curated"] is True and len(body["highlights"]) >= 3
    assert all(h["title"] and h["blurb"] for h in body["highlights"])
    assert body["season"] and body["tip"] and body["source"].startswith("https://") and body["as_of"]


def test_an_uncurated_country_is_an_honest_empty_shape_not_an_invention():
    body = client.get("/api/destination/BRA").json()
    assert body["curated"] is False and body["highlights"] == [] and body["source"] is None


def test_an_unknown_country_is_a_422():
    assert client.get("/api/destination/ZZZ").status_code == 422


def test_curated_copy_has_no_prices_or_digits():
    for iso, entry in destination._data()["destinations"].items():
        text = json.dumps(entry)
        assert not any(c.isdigit() for c in text.replace("https://", "")), iso


def test_the_fixture_matches_the_live_shape():
    assert json.loads(FIXTURE.read_text()).keys() == client.get("/api/destination/ARE").json().keys()
