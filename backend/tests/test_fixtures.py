import json
from datetime import date
from pathlib import Path

import pytest

from visa_roulette.bcbp import build_bcbp, parse_bcbp
from visa_roulette.mrz import is_valid_for_months, parse_td3
from tests.test_bcbp import sample

MANIFEST = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "manifest.json").read_text())
BY_KEY = {p["key"]: p for p in MANIFEST}
TRAVEL_DAY = date(2026, 10, 11)


def full_name(mrz) -> str:
    return f"{mrz.given_names} {mrz.surname}"


@pytest.mark.parametrize("persona", MANIFEST, ids=lambda p: p["key"])
def test_props_are_internally_valid(persona):
    mrz = parse_td3(*persona["mrz"])
    assert mrz.all_checks_pass
    assert mrz.nationality == "IND"
    boarding = parse_bcbp(persona["bcbp"], year=2026)
    assert (boarding.origin, boarding.destination) == ("CCJ", "DXB")
    assert boarding.surname == mrz.surname


def test_lakshmi_trap_is_short_passport_validity():
    mrz = parse_td3(*BY_KEY["lakshmi"]["mrz"])
    assert not is_valid_for_months(mrz.expiry_date, TRAVEL_DAY)
    assert BY_KEY["lakshmi"]["expected"] == "HELD"


def test_arjun_is_clean():
    mrz = parse_td3(*BY_KEY["arjun"]["mrz"])
    assert is_valid_for_months(mrz.expiry_date, TRAVEL_DAY)
    assert BY_KEY["arjun"]["booking_name"] == full_name(mrz)
    assert BY_KEY["arjun"]["expected"] == "CLEARED"


def test_shafeeq_trap_is_name_mismatch():
    mrz = parse_td3(*BY_KEY["shafeeq"]["mrz"])
    assert BY_KEY["shafeeq"]["booking_name"] != full_name(mrz)
    assert BY_KEY["shafeeq"]["expected"] == "HELD"


def test_pdf417_barcode_scans_back_to_the_exact_string():
    pdf417gen = pytest.importorskip("pdf417gen")
    zxingcpp = pytest.importorskip("zxingcpp")
    data = build_bcbp(sample())
    img = pdf417gen.render_image(pdf417gen.encode(data, columns=8, security_level=3), scale=4, ratio=3, padding=12)
    assert data in [r.text for r in zxingcpp.read_barcodes(img.convert("RGB"))]
