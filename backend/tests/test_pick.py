import pytest
from fastapi.testclient import TestClient
from visa_roulette.api import create_app
from visa_roulette.pick import answer, deal

client = TestClient(create_app())
FLAWS = {"R-PP-VALIDITY-6M", "R-NAME-HOTEL", "R-NAME-RET"}


def test_every_deal_has_three_documents_with_no_flaw_flag_leaked():
    docs = deal("THA")
    assert [d["id"] for d in docs] == ["passport", "hotel", "return"]
    for doc in docs:
        assert set(doc) == {"id", "title", "lines"} and doc["lines"]


def test_a_deal_is_stable_for_a_destination():
    assert deal("THA") == deal("THA")


def test_the_flaw_varies_across_destinations():
    flawed = {answer(code, "passport")["flawed_id"] for code in ("THA", "GEO", "ARE", "JPN", "PER", "ISL", "NPL", "KEN")}
    assert len(flawed) == 3


def test_picking_the_flawed_document_is_correct_and_cites_its_rule():
    first = answer("THA", "passport")
    right = answer("THA", first["flawed_id"])
    assert right["correct"] is True
    assert right["rule"]["id"] in FLAWS
    assert right["rule"]["label"] and "verified" in right["rule"]


def test_picking_a_clean_document_is_wrong_but_still_reveals_the_real_flaw():
    flawed = answer("THA", "passport")["flawed_id"]
    clean = next(i for i in ("passport", "hotel", "return") if i != flawed)
    wrong = answer("THA", clean)
    assert wrong["correct"] is False and wrong["flawed_id"] == flawed
    assert wrong["rule"]["id"] in FLAWS


def test_the_reveal_explains_what_was_inconsistent():
    assert answer("THA", "passport")["explanation"]


def test_an_unknown_document_id_is_rejected():
    with pytest.raises(ValueError):
        answer("THA", "visa")


def test_the_deal_endpoint_returns_three_documents():
    out = client.get("/api/pick/THA")
    assert out.status_code == 200 and len(out.json()["documents"]) == 3


def test_the_deal_endpoint_rejects_an_unknown_country():
    assert client.get("/api/pick/ZZZ").status_code == 422


def test_the_answer_endpoint_reveals_the_rule():
    flawed = client.post("/api/pick/THA/answer", json={"choice": "passport"}).json()["flawed_id"]
    out = client.post("/api/pick/THA/answer", json={"choice": flawed}).json()
    assert out["correct"] is True and out["rule"]["source_url"]


def test_the_answer_endpoint_rejects_a_bad_choice():
    assert client.post("/api/pick/THA/answer", json={"choice": "visa"}).status_code == 422
