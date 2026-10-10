"""Pre-flight checklist: cited rules applied to passport, boarding pass, bookings and bag."""

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

from visa_roulette.bcbp import BoardingPass
from visa_roulette.mrz import TD3, is_valid_for_months
from visa_roulette.text import ascii_upper

_RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "checklist_rules.json"
_SEVERITY = {"fail": 3, "warn": 2, "manual": 1, "pass": 0}


@dataclass(frozen=True)
class Item:
    rule_id: str
    label: str
    status: str  # pass | fail | warn | manual | pending
    detail: str
    fix: str
    source_url: Optional[str]
    source_kind: str
    as_of: str
    verified: bool


@dataclass(frozen=True)
class Checklist:
    items: tuple
    verdict: str  # CLEARED | REVIEW | HELD
    readiness: float  # share of items that are passed


@lru_cache(maxsize=1)
def _rules() -> dict:
    return json.loads(_RULES_PATH.read_text())


def _item(rule_id: str, status: str, detail: str, fix: str = "") -> Item:
    rule = _rules()["rules"][rule_id]
    return Item(
        rule_id=rule_id,
        label=rule["label"],
        status=status,
        detail=detail,
        fix=fix,
        source_url=rule["source_url"],
        source_kind=rule["source_kind"],
        as_of=rule["as_of"],
        verified=rule["verified"],
    )


def _tokens(name: str) -> list:
    return re.findall(r"[A-Z0-9]+", ascii_upper(name).replace("/", " "))


def names_match(doc_name: str, passport_name: str, truncated: bool = False) -> bool:
    """Order- and case-insensitive name comparison. Spelling must match exactly.

    With truncated=True (boarding passes cut names at 20 chars) only the last
    token may be a prefix of a passport token.
    """
    doc, passport = _tokens(doc_name), _tokens(passport_name)
    if not truncated:
        return sorted(doc) == sorted(passport)
    if not doc:
        return False
    *head, last = doc
    remaining = list(passport)
    for token in head:
        if token not in remaining:
            return False
        remaining.remove(token)
    return any(candidate.startswith(last) for candidate in remaining)


def _expiry(expiry_date: str) -> Optional[date]:
    try:
        return date(2000 + int(expiry_date[0:2]), int(expiry_date[2:4]), int(expiry_date[4:6]))
    except ValueError:
        return None


def _months_after(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (1 if end.day < start.day else 0)


def _check_mrz(mrz: TD3) -> Item:
    if mrz.all_checks_pass:
        return _item("R-PP-CHECKS", "pass", "All check digits are valid.")
    bad = ", ".join(k.replace("_", " ") for k, ok in mrz.checks.items() if not ok)
    fix = "Rescan the passport page flat and well lit."
    return _item("R-PP-CHECKS", "fail", f"Check digit failed for: {bad}.", fix)


def _check_validity(mrz: TD3, travel_date: date) -> Item:
    expiry = _expiry(mrz.expiry_date)
    if expiry is None:
        return _item("R-PP-VALIDITY-6M", "fail", "The expiry date could not be read.", "Rescan the page.")
    if is_valid_for_months(mrz.expiry_date, travel_date):
        return _item("R-PP-VALIDITY-6M", "pass", f"Expires {expiry:%d %b %Y}.")
    if expiry <= travel_date:
        detail = f"Expired on {expiry:%d %b %Y}."
    else:
        months = _months_after(travel_date, expiry)
        detail = f"Expires {expiry:%d %b %Y}, only {months} month(s) after travel; 6 are required."
    return _item("R-PP-VALIDITY-6M", "fail", detail, "Renew the passport before you travel.")


def _check_name(
    rule_id: str, doc_name: Optional[str], passport_name: str, what: str, truncated: bool = False
) -> Item:
    if doc_name is None:
        return _item(rule_id, "pending", f"No {what} supplied to compare.")
    if names_match(doc_name, passport_name, truncated=truncated):
        return _item(rule_id, "pass", f"{doc_name} matches the passport.")
    return _item(
        rule_id,
        "fail",
        f"Name on the {what} ({doc_name}) differs from the passport ({passport_name}).",
        f"Ask the issuer to correct the {what} so it matches the passport exactly.",
    )


def _check_return(return_ticket_name: Optional[str]) -> Item:
    if return_ticket_name:
        return _item("R-RETURN-TICKET", "pass", "Return ticket found.")
    detail = "No return or onward ticket supplied."
    return _item("R-RETURN-TICKET", "fail", detail, "Book a return or onward ticket.")


def _bag_items(bag: Sequence[str]) -> list:
    specs = _rules()["bag_items"]
    grouped: dict = {}
    unmatched = []
    for entry in bag:
        lowered = entry.lower()
        spec = next((s for s in specs if any(term in lowered for term in s["terms"])), None)
        if spec is None:
            unmatched.append(entry)
            continue
        grouped.setdefault(spec["rule_id"], []).append((entry, spec["status"], spec["note"]))

    items = []
    for rule_id, entries in grouped.items():
        worst = max((status for _, status, _ in entries), key=_SEVERITY.__getitem__)
        detail = " ".join(f"{name}: {note}" for name, _, note in entries)
        fix = next((note for _, status, note in entries if status == worst and worst != "pass"), "")
        items.append(_item(rule_id, worst, detail, fix))
    if unmatched:
        names = ", ".join(unmatched)
        detail = f"Not in the demo ruleset: {names}. Check airline and customs rules."
        items.append(_item("R-BAG-GENERAL", "pass", detail))
    return items


def _manual_items(has_medicines: bool, ticked: frozenset) -> list:
    rule_ids = ["R-MAN-INSURANCE", "R-MAN-FUNDS"] + (["R-MAN-RX-COPY"] if has_medicines else [])
    return [
        _item(rid, "pass", "Confirmed by the traveller.")
        if rid in ticked
        else _item(rid, "manual", "Tap to confirm.")
        for rid in rule_ids
    ]


def build_checklist(
    *,
    mrz: TD3,
    boarding: BoardingPass,
    return_ticket_name: Optional[str],
    hotel_name: Optional[str],
    bag: Sequence[str],
    travel_date: date,
    ticked: frozenset = frozenset(),
) -> Checklist:
    passport_name = f"{mrz.given_names} {mrz.surname}"
    boarding_name = f"{boarding.surname}/{boarding.given_names}"
    bag_items = _bag_items(bag)
    items = (
        _check_mrz(mrz),
        _check_validity(mrz, travel_date),
        _check_name("R-NAME-BP", boarding_name, passport_name, "boarding pass", len(boarding_name) >= 19),
        _check_name("R-NAME-RET", return_ticket_name, passport_name, "return ticket"),
        _check_name("R-NAME-HOTEL", hotel_name, passport_name, "hotel booking"),
        _check_return(return_ticket_name),
        *bag_items,
        *_manual_items(any(i.rule_id == "R-BAG-MEDS" for i in bag_items), ticked),
    )
    statuses = {i.status for i in items}
    verdict = "HELD" if "fail" in statuses else "REVIEW" if "warn" in statuses else "CLEARED"
    readiness = sum(i.status == "pass" for i in items) / len(items)
    return Checklist(items=items, verdict=verdict, readiness=readiness)
