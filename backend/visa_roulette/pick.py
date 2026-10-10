"""Wrong-Document Pick: three papers for a made-up traveller, one breaks a cited checklist rule.

Deterministic per destination, so the booth, a phone and the tests all see the same deal. No real passport data.
"""

import zlib

from visa_roulette import geo
from visa_roulette.checklist import rule_info

TRAVELLER = "PRIYA NAIR"
LOOKALIKE = "PRIYA NAYAR"
ARRIVAL = "12 OCT 2026"
GOOD_EXPIRY = "14 MAY 2029"
SHORT_EXPIRY = "09 JAN 2027"
DOC_IDS = ("passport", "hotel", "return")

_FLAWS = (
    ("passport", "R-PP-VALIDITY-6M", f"The passport expires {SHORT_EXPIRY}, under six months after arrival on {ARRIVAL}."),
    ("hotel", "R-NAME-HOTEL", f"The hotel booking says {LOOKALIKE}, the passport says {TRAVELLER}."),
    ("return", "R-NAME-RET", f"The return ticket says {LOOKALIKE}, the passport says {TRAVELLER}."),
)


def _flaw(iso3: str) -> tuple:
    return _FLAWS[zlib.crc32(iso3.encode()) % len(_FLAWS)]


def deal(iso3: str) -> list:
    place = geo.country_name(iso3)
    flawed = _flaw(iso3)[0]
    return [
        {"id": "passport", "title": "Passport", "lines": [TRAVELLER, f"Expires {SHORT_EXPIRY if flawed == 'passport' else GOOD_EXPIRY}"]},
        {"id": "hotel", "title": "Hotel booking", "lines": [LOOKALIKE if flawed == "hotel" else TRAVELLER, f"3 nights, {place}"]},
        {"id": "return", "title": "Return ticket", "lines": [f"Passenger {LOOKALIKE if flawed == 'return' else TRAVELLER}", f"Leaves {place} 3 days after {ARRIVAL}"]},
    ]


def answer(iso3: str, choice: str) -> dict:
    if choice not in DOC_IDS:
        raise ValueError(f"unknown document: {choice}")
    flawed_id, rule_id, explanation = _flaw(iso3)
    return {"correct": choice == flawed_id, "flawed_id": flawed_id, "rule": rule_info(rule_id), "explanation": explanation}
