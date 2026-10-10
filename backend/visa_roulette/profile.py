"""The traveller profile collected before the throw. Optional fields stay optional; nothing leaves the laptop."""

from datetime import date
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from visa_roulette.geo import is_country
from visa_roulette.mrz import TD3, birth_to_date

PassportType = Literal["ordinary", "diplomatic", "official", "emergency", "refugee"]
Gender = Literal["female", "male", "nonbinary", "undisclosed"]
VisaKind = Literal["tourist", "business", "transit", "student", "work", "residence", "evisa"]
Iso3 = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]

MAX_VISAS = 10
_MRZ_TYPE = {"D": "diplomatic", "O": "official", "S": "official"}
_MRZ_SEX = {"M": "male", "F": "female"}
_MRZ_COUNTRY = {"D": "DEU"}  # issuer codes that are not ISO 3166-1 alpha-3


def _known_country(code: str) -> str:
    if not is_country(code):
        raise ValueError(f"unknown country code: {code}")
    return code


class VisaHeld(BaseModel):
    model_config = ConfigDict(frozen=True)

    country: Iso3
    kind: VisaKind
    valid_until: date | None = None

    _country_exists = field_validator("country")(_known_country)


class TravelerProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    origin: Iso3  # where the traveller is now; the throw starts here
    nationality: Iso3
    age: int = Field(ge=0, le=120)
    gender: Gender = "undisclosed"
    name: str | None = Field(default=None, max_length=80)
    passport_type: PassportType | None = None  # None: no passport yet
    visas: list[VisaHeld] = Field(default_factory=list, max_length=MAX_VISAS)

    _origin_exists = field_validator("origin")(_known_country)
    _nationality_exists = field_validator("nationality")(_known_country)

    @field_validator("name")
    @classmethod
    def tidy_name(cls, value: str | None) -> str | None:
        cleaned = " ".join((value or "").split()).upper()
        return cleaned or None

    @model_validator(mode="after")
    def visas_need_a_passport(self) -> "TravelerProfile":
        if self.visas and self.passport_type is None:
            raise ValueError("a visa needs a passport to be attached to")
        return self


def _age_on(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def prefill_from_mrz(td3: TD3, line1: str, today: date) -> dict:
    """Profile fields a scanned passport can answer. Origin and visas are never guessed."""
    given = td3.given_names.strip()
    name = " ".join(part for part in (given, td3.surname.strip()) if part)
    return {
        "nationality": _MRZ_COUNTRY.get(td3.nationality, td3.nationality),
        "gender": _MRZ_SEX.get(td3.sex, "undisclosed"),
        "age": _age_on(birth_to_date(td3.birth_date, today), today),
        "name": name or None,
        "passport_type": _MRZ_TYPE.get(line1[1:2], "ordinary"),
    }
