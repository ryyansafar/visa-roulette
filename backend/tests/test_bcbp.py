from datetime import date

import pytest

from visa_roulette.bcbp import BoardingPass, build_bcbp, parse_bcbp


def sample() -> BoardingPass:
    return BoardingPass(
        surname="NAIR",
        given_names="LAKSHMI",
        pnr="LAYOV01",
        origin="CCJ",
        destination="DXB",
        carrier="ZZ",
        flight="0123",
        flight_date=date(2026, 10, 10),
        cabin="Y",
        seat="014A",
        sequence="0007",
    )


def test_mandatory_block_is_60_chars_after_header():
    s = build_bcbp(sample())
    assert s.startswith("M1")
    assert len(s) == 60


def test_round_trip():
    original = sample()
    parsed = parse_bcbp(build_bcbp(original), year=2026)
    assert parsed == original


def test_julian_day_is_encoded():
    s = build_bcbp(sample())
    # 10 Oct 2026 is day 283 of the year
    assert "283" in s


def test_long_names_are_truncated_to_20_chars():
    bp = BoardingPass(**{**sample().__dict__, "surname": "A" * 30, "given_names": "B" * 30})
    s = build_bcbp(bp)
    assert len(s) == 60
    assert s[2:22] == ("A" * 30 + "/" + "B" * 30)[:20]


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_bcbp("not a boarding pass", year=2026)
