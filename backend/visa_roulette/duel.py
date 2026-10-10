"""Passport duel: two passports, one destination, side-by-side verdicts. Stateless, nothing is stored."""

from dataclasses import asdict
from typing import Iterable, Optional

from visa_roulette.visa import needs, requirement

_STRENGTH = {"home": 0, "held": 0, "free": 0, "on_arrival": 1, "evisa": 2, "required": 3}


def strength(status: str) -> Optional[int]:
    """Lower is easier entry. A status with no ranking (unknown) cannot win or lose."""
    return _STRENGTH.get(status)


def _side(nationality: str, destination: str, visas: Iterable) -> dict:
    verdict = requirement(nationality, destination, visas)
    return {"nationality": nationality, "verdict": asdict(verdict), "needs": needs(verdict.status, destination)}


def _winner(a: dict, b: dict) -> Optional[str]:
    a_rank, b_rank = strength(a["verdict"]["status"]), strength(b["verdict"]["status"])
    if a_rank is None or b_rank is None or a_rank == b_rank:
        return None
    return "a" if a_rank < b_rank else "b"


def duel(a_nationality: str, b_nationality: str, destination: str, a_visas: Iterable = (), b_visas: Iterable = ()) -> dict:
    a = _side(a_nationality, destination, a_visas)
    b = _side(b_nationality, destination, b_visas)
    return {"destination": destination, "a": a, "b": b, "winner": _winner(a, b)}
