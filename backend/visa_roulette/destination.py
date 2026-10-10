"""Curated outdoor-scene copy for a destination: what the place offers once you are through immigration."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from visa_roulette import geo

PATH = Path(__file__).resolve().parents[2] / "rules" / "destinations.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(PATH.read_text())


def lookup(iso3: str) -> Optional[dict]:
    if not geo.is_country(iso3):
        return None
    data = _data()
    entry = data["destinations"].get(iso3)
    if entry is None:
        return {"iso3": iso3, "name": geo.country_name(iso3), "highlights": [], "season": None, "tip": None, "source": None, "as_of": data["as_of"], "curated": False}
    return {"iso3": iso3, "name": geo.country_name(iso3), **entry, "as_of": data["as_of"], "curated": True}
