"""Robustness cases found in code review: OCR garbage, bad dates, field widths, diacritics."""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from visa_roulette.bcbp import build_bcbp, parse_bcbp
from visa_roulette.mrz import (
    birth_to_date,
    build_td3,
    is_valid_for_months,
    parse_td3_ocr,
)

from tests.test_bcbp import sample

ICAO_LINE1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
ICAO_LINE2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
TD3_KW = dict(
    given_names="ANNA",
    document_number="L898902C3",
    nationality="UTO",
    birth_date="740812",
    sex="F",
    expiry_date="120415",
    issuer="UTO",
)


# --- MRZ -----------------------------------------------------------------

def test_guillemet_and_unicode_noise_do_not_raise():
    for noisy in (
        ICAO_LINE2[:3] + "«" + ICAO_LINE2[4:],
        ICAO_LINE2[:9] + "²" + ICAO_LINE2[10:],
        ICAO_LINE2[:3] + "?" + ICAO_LINE2[4:],
    ):
        mrz = parse_td3_ocr(ICAO_LINE1, noisy)
        assert not mrz.all_checks_pass


def test_non_string_input_is_a_value_error():
    with pytest.raises(ValueError):
        parse_td3_ocr(None, "x")


def test_impossible_expiry_dates_are_simply_invalid():
    today = date(2026, 10, 10)
    assert not is_valid_for_months("261340", today)
    assert not is_valid_for_months("<<<<<<", today)


def test_birth_date_century_pivot():
    today = date(2026, 10, 10)
    assert birth_to_date("640305", today) == date(1964, 3, 5)
    assert birth_to_date("020714", today) == date(2002, 7, 14)
    assert birth_to_date("261231", today) == date(1926, 12, 31)  # would be in the future as 2026


def test_builder_transliterates_diacritics():
    line1, _ = build_td3(surname="MÜLLER", **TD3_KW)
    assert line1.startswith("P<UTOMULLER<<ANNA")
    line1, _ = build_td3(surname="O'BRIEN", **{**TD3_KW, "given_names": "JOSÉ"})
    assert line1.startswith("P<UTOOBRIEN<<JOSE")


def test_builder_normalises_document_number_case():
    _, line2 = build_td3(surname="X", **{**TD3_KW, "document_number": "l898902c3"})
    assert line2.startswith("L898902C3")


@pytest.mark.parametrize(
    "override",
    [
        {"birth_date": "64035"},
        {"expiry_date": "12041X"},
        {"sex": "Q"},
        {"document_number": "ABCDEFGHIJ"},
        {"personal_number": "X" * 15},
    ],
)
def test_builder_rejects_bad_fields(override):
    with pytest.raises(ValueError):
        build_td3(surname="ERIKSSON", **{**TD3_KW, **override})


# --- BCBP ----------------------------------------------------------------

def _with_day(data: str, day: str) -> str:
    return data[:44] + day + data[47:]


@pytest.mark.parametrize("day", ["000", "367", "999", " 36", "+01", "-01", "ABC"])
def test_bcbp_rejects_bad_day_of_year(day):
    with pytest.raises(ValueError):
        parse_bcbp(_with_day(build_bcbp(sample()), day), year=2026)


def test_bcbp_day_366_only_in_leap_years():
    data = _with_day(build_bcbp(sample()), "366")
    assert parse_bcbp(data, year=2028).flight_date == date(2028, 12, 31)
    with pytest.raises(ValueError):
        parse_bcbp(data, year=2026)


def test_bcbp_non_string_input_is_a_value_error():
    with pytest.raises(ValueError):
        parse_bcbp(None, year=2026)


@pytest.mark.parametrize(
    "field,value",
    [("pnr", "ABCDEFGHI"), ("origin", "CALICUT"), ("carrier", "ABCD"),
     ("flight", "ABCDEF"), ("seat", "12345"), ("sequence", "123456"), ("cabin", "YY")],
)
def test_bcbp_builder_rejects_overlong_fields(field, value):
    with pytest.raises(ValueError):
        build_bcbp(replace(sample(), **{field: value}))


def test_bcbp_builder_cleans_names():
    bp = replace(sample(), surname="O'BRÜEN", given_names="JOSÉ")
    data = build_bcbp(bp)
    assert data[2:22].strip() == "OBRUEN/JOSE"
    assert len(data) == 60


# --- Props ---------------------------------------------------------------

def test_every_prop_mrz_carries_a_specimen_marker():
    manifest = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "manifest.json").read_text())
    for persona in manifest:
        assert "SPECIMEN" in persona["mrz"][1]
