from datetime import date

import pytest
from visa_roulette.mrz import (
    build_td3,
    check_digit,
    is_valid_for_months,
    normalize_td3,
    parse_td3,
    parse_td3_ocr,
)

# ICAO Doc 9303 specimen (fictional state "UTO"), the standard published test vector.
ICAO_LINE1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
ICAO_LINE2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_check_digit_known_values():
    assert check_digit("L898902C3") == 6
    assert check_digit("740812") == 2
    assert check_digit("120415") == 9
    assert check_digit("ZE184226B<<<<<") == 1


def test_check_digit_treats_filler_as_zero():
    assert check_digit("<<<<<<") == 0


def test_parse_icao_specimen_is_fully_valid():
    mrz = parse_td3(ICAO_LINE1, ICAO_LINE2)
    assert mrz.surname == "ERIKSSON"
    assert mrz.given_names == "ANNA MARIA"
    assert mrz.document_number == "L898902C3"
    assert mrz.nationality == "UTO"
    assert mrz.birth_date == "740812"
    assert mrz.sex == "F"
    assert mrz.expiry_date == "120415"
    assert mrz.all_checks_pass


def test_parse_flags_a_tampered_document_number():
    bad = ICAO_LINE2.replace("L898902C3", "L898902C4")
    mrz = parse_td3(ICAO_LINE1, bad)
    assert not mrz.checks["document_number"]
    assert not mrz.all_checks_pass


def test_parse_rejects_wrong_length():
    with pytest.raises(ValueError):
        parse_td3(ICAO_LINE1[:-1], ICAO_LINE2)


def test_build_round_trips_through_parse():
    line1, line2 = build_td3(
        surname="NAIR",
        given_names="LAKSHMI AMMAL",
        document_number="Z1234567",
        nationality="IND",
        birth_date="640305",
        sex="F",
        expiry_date="270310",
        issuer="IND",
    )
    assert len(line1) == 44 and len(line2) == 44
    mrz = parse_td3(line1, line2)
    assert mrz.surname == "NAIR"
    assert mrz.given_names == "LAKSHMI AMMAL"
    assert mrz.all_checks_pass


def test_build_matches_icao_specimen():
    line1, line2 = build_td3(
        surname="ERIKSSON",
        given_names="ANNA MARIA",
        document_number="L898902C3",
        nationality="UTO",
        birth_date="740812",
        sex="F",
        expiry_date="120415",
        issuer="UTO",
        personal_number="ZE184226B",
    )
    assert line1 == ICAO_LINE1
    assert line2 == ICAO_LINE2


LAKSHMI = (
    "P<INDNAIR<<LAKSHMI<AMMAL<<<<<<<<<<<<<<<<<<<<",
    "Z1234567<1IND6403050F2703109<<<<<<<<<<<<<<04",
)
ARJUN = (
    "P<INDMENON<<ARJUN<<<<<<<<<<<<<<<<<<<<<<<<<<<",
    "Z7654321<9IND0207142M3308154<<<<<<<<<<<<<<08",
)


def test_normalize_fixes_letter_for_zero_in_check_digit():
    # real Tesseract output: composite digit '04' read as 'Q4'
    noisy_line2 = LAKSHMI[1][:-2] + "Q4"
    mrz = parse_td3_ocr(LAKSHMI[0], noisy_line2)
    assert mrz.all_checks_pass


def test_normalize_fixes_letter_for_zero_in_dates():
    # real Tesseract output: birth date '020714' read as 'O20714'
    noisy_line2 = ARJUN[1].replace("0207142", "O207142")
    mrz = parse_td3_ocr(ARJUN[0], noisy_line2)
    assert mrz.birth_date == "020714"
    assert mrz.all_checks_pass


def test_normalize_pads_dropped_filler_characters():
    # real Tesseract output: line 1 came back 43 characters long
    mrz = parse_td3_ocr(ARJUN[0][:-1], ARJUN[1])
    assert mrz.surname == "MENON"
    assert mrz.all_checks_pass


def test_normalize_is_a_no_op_on_clean_input():
    assert normalize_td3(*LAKSHMI) == LAKSHMI


def test_ocr_cannot_launder_a_genuinely_wrong_check_digit():
    wrong = LAKSHMI[1].replace("Z1234567", "Z1234568")
    assert not parse_td3_ocr(LAKSHMI[0], wrong).all_checks_pass


def test_six_month_validity_rule():
    today = date(2026, 10, 10)
    assert not is_valid_for_months("270310", today, months=6)  # ~5 months left
    assert is_valid_for_months("330101", today, months=6)
    assert not is_valid_for_months("200101", today, months=6)  # already expired
