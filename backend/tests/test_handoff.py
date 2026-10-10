from datetime import date

import pytest
import zxingcpp
from PIL import Image
from visa_roulette.handoff import Handoff, decode_handoff, encode_handoff, qr_matrix
from visa_roulette.profile import TravelerProfile

PROFILE = TravelerProfile(
    origin="IND", nationality="IND", age=24, gender="male", name="ARJUN MENON", passport_type="ordinary",
    visas=[{"country": "ARE", "kind": "tourist", "valid_until": "2027-01-01"}],
)


def make(**kw):
    base = dict(
        profile=PROFILE, landing_iso3="ARE", lat=25.2, lon=55.3,
        budget=1500, currency="USD", consent=True, issued=date(2026, 10, 10),
    )
    return Handoff(**{**base, **kw})


def test_round_trip_preserves_everything():
    original = make()
    assert decode_handoff(encode_handoff(original)) == original


def test_payload_is_prefixed_and_small_enough_for_a_scannable_qr():
    text = encode_handoff(make())
    assert text.startswith("VR1.") and len(text) < 600


def test_no_consent_no_qr():
    with pytest.raises(ValueError):
        encode_handoff(make(consent=False))


@pytest.mark.parametrize("budget", [-1, 0, 10_000_001])
def test_budget_must_be_positive_and_sane(budget):
    with pytest.raises(ValueError):
        make(budget=budget)


def test_tampered_or_foreign_text_is_rejected():
    text = encode_handoff(make())
    for bad in (text[:-6], "VR2." + text[4:], "hello", text.replace(".", ":", 1), ""):
        with pytest.raises(ValueError):
            decode_handoff(bad)


def test_unknown_destination_is_rejected():
    with pytest.raises(ValueError):
        make(landing_iso3="XXX")


def test_matrix_is_square_and_decodes_back_to_the_payload():
    text = encode_handoff(make())
    matrix = qr_matrix(text)
    assert len(matrix) == len(matrix[0]) and all(len(r) == len(matrix) for r in matrix)
    scale, border = 8, 4
    size = (len(matrix) + 2 * border) * scale
    img = Image.new("L", (size, size), 255)
    px = img.load()
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                for dy in range(scale):
                    for dx in range(scale):
                        px[(x + border) * scale + dx, (y + border) * scale + dy] = 0
    assert [r.text for r in zxingcpp.read_barcodes(img)] == [text]
