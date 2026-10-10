import json
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

import pytest
from visa_roulette.bcbp import parse_bcbp
from visa_roulette.checklist import build_checklist, names_match
from visa_roulette.mrz import parse_td3

MANIFEST = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "manifest.json").read_text())
BY_KEY = {p["key"]: p for p in MANIFEST}
TRAVEL_DAY = date(2026, 10, 11)


def run(key: str, **overrides):
    persona = BY_KEY[key]
    kwargs = dict(
        mrz=parse_td3(*persona["mrz"]),
        boarding=parse_bcbp(persona["bcbp"], year=2026),
        return_ticket_name=persona["booking_name"],
        hotel_name=persona["booking_name"],
        bag=persona["bag"],
        travel_date=TRAVEL_DAY,
    )
    return build_checklist(**{**kwargs, **overrides})


def item(checklist, rule_id: str):
    return next(i for i in checklist.items if i.rule_id == rule_id)


@pytest.mark.parametrize("key", ["lakshmi", "arjun", "shafeeq"])
def test_verdict_matches_the_manifest(key):
    assert run(key).verdict == BY_KEY[key]["expected"]


def test_lakshmi_fails_on_passport_validity_with_a_fix():
    result = run("lakshmi")
    validity = item(result, "R-PP-VALIDITY-6M")
    assert validity.status == "fail"
    assert "renew" in validity.fix.lower()
    assert "month" in validity.detail.lower()
    assert item(result, "R-PP-CHECKS").status == "pass"


def test_lakshmi_bag_is_flagged_for_review_not_banned():
    bag = item(run("lakshmi"), "R-BAG-FOOD")
    assert bag.status == "warn"
    assert bag.verified is False


def test_shafeeq_fails_name_match_on_return_ticket_and_hotel():
    result = run("shafeeq")
    for rule in ("R-NAME-RET", "R-NAME-HOTEL"):
        assert item(result, rule).status == "fail"
        assert "differ" in item(result, rule).detail.lower()
    assert item(result, "R-PP-VALIDITY-6M").status == "pass"


def test_arjun_has_no_failures_or_warnings():
    result = run("arjun")
    assert {i.status for i in result.items if i.rule_id.startswith(("R-PP", "R-NAME", "R-RET"))} == {"pass"}
    assert result.verdict == "CLEARED"


def test_tampered_passport_fails_the_mrz_item():
    line1, line2 = BY_KEY["arjun"]["mrz"]
    tampered = parse_td3(line1, line2.replace("Z7654321", "Z7654322"))
    assert item(run("arjun", mrz=tampered), "R-PP-CHECKS").status == "fail"


def test_ticking_a_manual_item_marks_it_done():
    pending = run("arjun")
    done = run("arjun", ticked=frozenset({"R-MAN-INSURANCE"}))
    assert item(pending, "R-MAN-INSURANCE").status == "manual"
    assert item(done, "R-MAN-INSURANCE").status == "pass"
    assert done.readiness > pending.readiness


def test_missing_return_ticket_fails():
    result = run("arjun", return_ticket_name=None)
    assert item(result, "R-RETURN-TICKET").status == "fail"


def test_every_item_carries_its_evidence_fields():
    for i in run("lakshmi").items:
        assert i.rule_id and i.as_of and isinstance(i.verified, bool)


def test_results_are_immutable():
    result = run("arjun")
    assert isinstance(result.items, tuple)
    with pytest.raises(FrozenInstanceError):
        result.items[0].status = "pass"


def test_name_matching_ignores_order_and_case_but_not_spelling():
    assert names_match("LAKSHMI AMMAL NAIR", "NAIR LAKSHMI AMMAL")
    assert names_match("lakshmi ammal nair", "NAIR LAKSHMI AMMAL")
    assert not names_match("MOHAMED SHAFIQ", "SHAFEEQ MOHAMMED")


def test_truncated_boarding_pass_names_are_tolerated():
    assert names_match("NAIR/LAKSHMI AMMA", "LAKSHMI AMMAL NAIR", truncated=True)
    assert not names_match("NAIR/LAKSHMI AMMA", "LAKSHMI AMMAL NAIR", truncated=False)
