"""Tonight's landings wall: every opted-in landing, newest first, plus the night's headline numbers.

Read-only over the souvenir journal. No passport data: only the nickname, the two countries and the verdict.
"""

from collections import Counter
from collections.abc import Iterable

from visa_roulette.visa import LABELS, requirement

TICKER_SIZE = 12
PIN_LIMIT = 300


def _entry(souvenir) -> dict:
    nationality = souvenir.nationality or souvenir.origin
    status = souvenir.status or requirement(nationality, souvenir.landing_iso3).status
    return {
        "nickname": souvenir.nickname,
        "origin": souvenir.origin,
        "nationality": nationality,
        "iso3": souvenir.landing_iso3,
        "status": status,
        "label": LABELS[status],
        "seeded": souvenir.seeded,
    }


def _luckiest(entries: list):
    by_passport = {}
    for entry in entries:
        free, total = by_passport.get(entry["nationality"], (0, 0))
        by_passport[entry["nationality"]] = (free + (entry["status"] == "free"), total + 1)
    if not by_passport:
        return None
    best = max(by_passport.items(), key=lambda item: (item[1][0] / item[1][1], item[1][1], item[0]))
    return {"nationality": best[0], "rate": round(best[1][0] / best[1][1], 2), "landings": best[1][1]}


def build_wall(souvenirs: Iterable, ticker_size: int = TICKER_SIZE) -> dict:
    entries = [_entry(s) for s in souvenirs]
    landed = Counter(e["iso3"] for e in entries)
    top = min(landed.items(), key=lambda item: (-item[1], item[0])) if landed else None
    free = sum(e["status"] == "free" for e in entries)
    return {
        "pins": [{"iso3": e["iso3"], "status": e["status"], "seeded": e["seeded"]} for e in entries[-PIN_LIMIT:]],
        "ticker": entries[::-1][:ticker_size],
        "stats": {
            "total": len(entries),
            "visa_free_rate": round(free / len(entries), 2) if entries else 0.0,
            "most_landed": {"iso3": top[0], "count": top[1]} if top else None,
            "luckiest_passport": _luckiest(entries),
        },
    }
