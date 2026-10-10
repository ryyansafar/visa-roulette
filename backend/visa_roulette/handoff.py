"""The QR hand-off: everything the phone needs, self-contained, so the phone page works with no internet.

Text format: "VR1." + base64url(zlib(compact JSON)). zlib's checksum catches a damaged scan.
Only what the phone page shows is carried: the passport number and MRZ never leave the laptop.
"""

import base64
import json
import zlib
from datetime import date
from typing import Annotated, Literal, Optional

import qrcode
from pydantic import BaseModel, ConfigDict, Field, field_validator

from visa_roulette.geo import is_country
from visa_roulette.profile import TravelerProfile
from visa_roulette.souvenirs import Souvenir

PREFIX = "VR1."
MAX_BUDGET = 10_000_000


class VisaVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str = Field(max_length=16)
    label: str = Field(max_length=60)
    as_of: str = Field(max_length=10)
    source_url: Optional[str] = Field(default=None, max_length=120)


class Preflight(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Literal["CLEARED", "REVIEW", "HELD"]
    readiness: int = Field(ge=0, le=100)


class Handoff(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: TravelerProfile
    landing_iso3: str = Field(pattern=r"^[A-Z]{3}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    budget: int = Field(gt=0, le=MAX_BUDGET)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    consent: bool
    issued: date
    visa: Optional[VisaVerdict] = None
    preflight: Optional[Preflight] = None
    needs: list[Annotated[str, Field(max_length=48)]] = Field(default_factory=list, max_length=8)
    stranger: Optional[Souvenir] = None

    @field_validator("landing_iso3")
    @classmethod
    def destination_exists(cls, code: str) -> str:
        if not is_country(code):
            raise ValueError(f"unknown country code: {code}")
        return code


def encode_handoff(handoff: Handoff) -> str:
    if not handoff.consent:
        raise ValueError("the traveller has not agreed to this trip")
    document = handoff.model_dump(mode="json", exclude_none=True)
    raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode().rstrip("=")


def decode_handoff(text: str) -> Handoff:
    if not isinstance(text, str) or not text.startswith(PREFIX):
        raise ValueError("not a Visa Roulette code")
    body = text[len(PREFIX):]
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return Handoff.model_validate(json.loads(raw))
    except (zlib.error, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("this code is damaged or incomplete") from exc


def qr_matrix(text: str) -> list:
    """Module grid (True = dark, no quiet zone) so the browser can animate the plane into it."""
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=0)
    code.add_data(text)
    code.make(fit=True)
    return code.get_matrix()
