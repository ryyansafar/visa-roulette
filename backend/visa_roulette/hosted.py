"""Hosted mode (Vercel): what the booth does with hardware and heavy libraries it does not have.

At the booth every scanner runs for real. On a serverless host there is no Tesseract binary, no camera, no ESP32 and no
local model, so those paths answer with a clear 503 instead of crashing at import time. The one exception is the sample
travellers: their prop images are known files, so a byte-identical upload is answered from the fixture manifest and the
hosted demo checklist still works end to end. Anything else is never guessed at.
"""

import hashlib
import importlib.util
import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

from visa_roulette.errors import ScanError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
UNAVAILABLE_CODE = "unavailable_on_hosted"
UNAVAILABLE_MESSAGE = "Camera scanning only works at the booth. Pick one of the sample travellers here."


def is_hosted() -> bool:
    """True on Vercel (it sets VERCEL) or when VISA_ROULETTE_HOSTED is set to anything non-empty."""
    return bool(os.environ.get("VISA_ROULETTE_HOSTED") or os.environ.get("VERCEL"))


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def can_read_boarding() -> bool:
    return _has("PIL") and _has("zxingcpp")


def can_read_passport() -> bool:
    return _has("PIL") and shutil.which("tesseract") is not None


def unavailable() -> ScanError:
    return ScanError(UNAVAILABLE_CODE, UNAVAILABLE_MESSAGE, 503)


@lru_cache(maxsize=1)
def _index() -> dict:
    """sha256 of each sample passport and boarding-pass image, mapped to what the manifest says is on it."""
    manifest = FIXTURES / "manifest.json"
    if not manifest.is_file():
        return {}
    found = {}
    for person in json.loads(manifest.read_text()):
        for prop, payload in (("passport", ("mrz", person.get("mrz"))), ("boarding_pass", ("bcbp", person.get("bcbp")))):
            image = FIXTURES / person["key"] / f"{prop}.png"
            if image.is_file() and payload[1]:
                found[(prop, hashlib.sha256(image.read_bytes()).hexdigest())] = payload[1]
    return found


def passport_fixture(data: bytes) -> list[str] | None:
    """The two MRZ lines of a sample passport image, or None for any other bytes."""
    return _index().get(("passport", hashlib.sha256(data).hexdigest()))


def boarding_fixture(data: bytes) -> str | None:
    """The BCBP string of a sample boarding-pass image, or None for any other bytes."""
    return _index().get(("boarding_pass", hashlib.sha256(data).hexdigest()))
