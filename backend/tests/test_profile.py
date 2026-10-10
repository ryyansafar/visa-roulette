from datetime import date

import pytest
from pydantic import ValidationError
from visa_roulette.mrz import parse_td3
from visa_roulette.profile import TravelerProfile, prefill_from_mrz

ARJUN = (
    "P<INDMENON<<ARJUN<<<<<<<<<<<<<<<<<<<<<<<<<<<",
    "Z7654321<9IND0207142M3308154SPECIMEN<<<<<<22",
)


def make(**overrides):
    base = {"origin": "IND", "nationality": "IND", "age": 24, "passport_type": "ordinary"}
    return TravelerProfile(**{**base, **overrides})


def test_minimal_profile_gets_safe_defaults():
    p = make(passport_type=None)
    assert p.gender == "undisclosed" and p.name is None and p.visas == []


def test_name_is_trimmed_and_uppercased():
    assert make(name="  arjun menon ").name == "ARJUN MENON"


@pytest.mark.parametrize("age", [-1, 121])
def test_age_must_be_plausible(age):
    with pytest.raises(ValidationError):
        make(age=age)


def test_unknown_country_is_rejected():
    with pytest.raises(ValidationError):
        make(nationality="XXX")


@pytest.mark.parametrize("kind", ["ordinary", "diplomatic", "official", "emergency", "refugee"])
def test_every_passport_kind_is_accepted(kind):
    assert make(passport_type=kind).passport_type == kind


def test_unknown_passport_kind_is_rejected():
    with pytest.raises(ValidationError):
        make(passport_type="golden")


def test_visa_without_a_passport_is_rejected():
    with pytest.raises(ValidationError):
        make(passport_type=None, visas=[{"country": "ARE", "kind": "tourist"}])


def test_visa_with_passport_is_kept_and_validated():
    p = make(visas=[{"country": "ARE", "kind": "tourist", "valid_until": "2027-01-01"}])
    assert p.visas[0].country == "ARE" and p.visas[0].valid_until == date(2027, 1, 1)
    with pytest.raises(ValidationError):
        make(visas=[{"country": "ZZZ", "kind": "tourist"}])


def test_too_many_visas_are_rejected():
    with pytest.raises(ValidationError):
        make(visas=[{"country": "ARE", "kind": "tourist"}] * 11)


def test_prefill_from_a_scanned_passport():
    fields = prefill_from_mrz(parse_td3(*ARJUN), ARJUN[0], today=date(2026, 10, 10))
    assert fields == {
        "nationality": "IND",
        "gender": "male",
        "age": 24,
        "name": "ARJUN MENON",
        "passport_type": "ordinary",
    }


def test_prefill_reads_passport_kind_from_the_mrz_type_letter():
    diplomatic = "PD" + ARJUN[0][2:]
    fields = prefill_from_mrz(parse_td3(diplomatic, ARJUN[1]), diplomatic, today=date(2026, 10, 10))
    assert fields["passport_type"] == "diplomatic"


def test_prefill_leaves_unspecified_sex_undisclosed():
    line2 = ARJUN[1][:20] + "<" + ARJUN[1][21:]
    fields = prefill_from_mrz(parse_td3(ARJUN[0], line2), ARJUN[0], today=date(2026, 10, 10))
    assert fields["gender"] == "undisclosed"


def test_prefill_maps_mrz_only_issuer_codes_to_iso3():
    line1 = "P<D<<MUELLER<<ANNA<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "C01X00T478" + "D<<" + "6408125" + "F" + "2701317" + "<" * 14 + "<" + "0"
    assert len(line2) == 44
    td3 = parse_td3(line1, line2)
    assert prefill_from_mrz(td3, line1, today=date(2026, 10, 10))["nationality"] == "DEU"
