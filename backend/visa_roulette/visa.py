"""Visa requirement lookup. Rules decide: a destination with no rule on file is "unknown", never guessed."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from visa_roulette.profile import VisaHeld

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "visa_rules.json"
STATUSES = ("free", "on_arrival", "evisa", "required")
LABELS = {
    "home": "Your own country",
    "held": "You already hold a visa",
    "free": "Visa-free",
    "on_arrival": "Visa on arrival",
    "evisa": "E-visa needed, apply online first",
    "required": "Visa needed, apply before you go",
    "unknown": "No rule on file",
}
CHECK_NOTE = "Check the official source before you travel."


@dataclass(frozen=True)
class Verdict:
    status: str
    label: str
    note: str
    source_url: str | None
    as_of: str
    verified: bool
    unlocked_by: str | None = None


@lru_cache(maxsize=1)
def _rules() -> dict:
    return json.loads(RULES_PATH.read_text())


def _verdict(status: str, note: str, unlocked_by: str | None = None) -> Verdict:
    rules = _rules()
    return Verdict(status, LABELS[status], note, rules["source_url"], rules["as_of"], rules["verified"], unlocked_by)


def _matching_visa(wanted: Iterable[str], held: list) -> str | None:
    schengen = set(_rules()["schengen"])
    for visa in held:
        if visa.country in wanted or ("SCHENGEN" in wanted and visa.country in schengen):
            return visa.country
    return None


def requirement(nationality: str, destination: str, held: Iterable[VisaHeld] = ()) -> Verdict:
    held = list(held)
    if nationality == destination:
        return _verdict("home", "You do not need a visa to enter your own country.")
    if any(visa.country == destination for visa in held):
        return _verdict("held", "Check that it is still valid and covers the dates of your stay.")

    entry = _rules()["nationalities"].get(nationality)
    if entry is None:
        return _verdict("unknown", f"No rules on file for this passport. {CHECK_NOTE}")

    for unlock in entry.get("unlocks", []):
        if unlock["destination"] == destination and (via := _matching_visa(unlock["if_held"], held)):
            return _verdict(unlock["status"], unlock["note"], via)
    for status in STATUSES:
        if destination in entry.get(status, []):
            return _verdict(status, CHECK_NOTE)
    return _verdict("unknown", f"No rule on file for this route. {CHECK_NOTE}")


def reachable(nationality: str, held: Iterable[VisaHeld] = ()) -> dict:
    """Status for every destination this passport has a rule for, held and unlocked visas included."""
    held = list(held)
    entry = _rules()["nationalities"].get(nationality, {})
    listed = {code for status in STATUSES for code in entry.get(status, [])}
    listed |= {unlock["destination"] for unlock in entry.get("unlocks", [])}
    listed |= {visa.country for visa in held}
    return {code: requirement(nationality, code, held).status for code in sorted(listed)}


def needs(status: str, destination: str) -> dict:
    """Documents a traveller typically needs for this verdict, plus any destination extras. Unverified like the rules."""
    docs = _rules()["documents"]
    base = [] if status in ("home", "unknown") else docs["base"]
    extra = docs["by_destination"].get(destination, {})
    items = [*base, *docs["by_status"].get(status, []), *(extra.get("extra", []) if status != "home" else [])]
    seen = set()
    unique = [item for item in items if not (item["id"] in seen or seen.add(item["id"]))]
    return {"items": unique, "official_url": extra.get("source_url"), "verified": False, "note": docs["note"]}
