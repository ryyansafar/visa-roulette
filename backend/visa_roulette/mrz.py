"""ICAO 9303 TD3 (passport) machine-readable zone: build, parse, validate."""

import calendar
import re
from dataclasses import dataclass
from datetime import date

from visa_roulette.text import ascii_upper

_WEIGHTS = (7, 3, 1)
_FILLER = "<"
_LINE_LEN = 44
_DIGITS = "0123456789"
_SEXES = frozenset("MFX<")


def _char_value(char: str) -> int:
    if char in _DIGITS:
        return int(char)
    if "A" <= char <= "Z":
        return ord(char) - ord("A") + 10
    if char == _FILLER:
        return 0
    raise ValueError(f"invalid MRZ character: {char!r}")


def check_digit(data: str) -> int:
    total = sum(_char_value(c) * _WEIGHTS[i % 3] for i, c in enumerate(data))
    return total % 10


def _clean(text: str) -> str:
    return re.sub(r"[^A-Z<]", "", ascii_upper(text).replace(" ", _FILLER).replace("-", _FILLER))


def _pad(text: str, length: int) -> str:
    return text[:length].ljust(length, _FILLER)


def _name_field(surname: str, given_names: str) -> str:
    return _pad(f"{_clean(surname)}{_FILLER * 2}{_clean(given_names)}", 39)


def _alnum(name: str, value: str, max_len: int, required: bool = True) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", ascii_upper(value))
    if (required and not cleaned) or len(cleaned) > max_len:
        raise ValueError(f"{name} must be 1-{max_len} letters/digits, got {value!r}")
    return cleaned


def _alpha3(name: str, value: str) -> str:
    cleaned = re.sub(r"[^A-Z]", "", ascii_upper(value))
    if not 1 <= len(cleaned) <= 3:
        raise ValueError(f"{name} must be 1-3 letters, got {value!r}")
    return cleaned


def _yymmdd(name: str, value: str) -> str:
    if not re.fullmatch(r"[0-9]{6}", value):
        raise ValueError(f"{name} must be YYMMDD digits, got {value!r}")
    return value


def build_td3(
    *,
    surname: str,
    given_names: str,
    document_number: str,
    nationality: str,
    birth_date: str,
    sex: str,
    expiry_date: str,
    issuer: str,
    personal_number: str = "",
) -> tuple[str, str]:
    if sex not in _SEXES:
        raise ValueError(f"sex must be one of M, F, X, <; got {sex!r}")
    birth = _yymmdd("birth_date", birth_date)
    expiry = _yymmdd("expiry_date", expiry_date)
    personal = _alnum("personal_number", personal_number, 14, required=False)

    line1 = f"P{_FILLER}{_pad(_alpha3('issuer', issuer), 3)}{_name_field(surname, given_names)}"
    doc = _pad(_alnum("document_number", document_number, 9), 9)
    personal_field = _pad(personal, 14)
    personal_cd = check_digit(personal_field) if personal else 0
    body = (
        f"{doc}{check_digit(doc)}{_pad(_alpha3('nationality', nationality), 3)}"
        f"{birth}{check_digit(birth)}{sex}"
        f"{expiry}{check_digit(expiry)}{personal_field}{personal_cd}"
    )
    composite = check_digit(body[0:10] + body[13:20] + body[21:43])
    return line1, f"{body}{composite}"


@dataclass(frozen=True)
class TD3:
    issuer: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    birth_date: str
    sex: str
    expiry_date: str
    personal_number: str
    checks: dict

    @property
    def all_checks_pass(self) -> bool:
        return all(self.checks.values())


def _digit_ok(field: str, claimed: str) -> bool:
    if len(claimed) != 1 or claimed not in _DIGITS:
        return False
    try:
        return check_digit(field) == int(claimed)
    except ValueError:
        return False


def parse_td3(line1: str, line2: str) -> TD3:
    if not isinstance(line1, str) or not isinstance(line2, str):
        raise ValueError("MRZ lines must be strings")
    if len(line1) != _LINE_LEN or len(line2) != _LINE_LEN:
        raise ValueError("TD3 MRZ lines must be 44 characters each")
    if line1[0] != "P":
        raise ValueError("not a passport MRZ (line 1 must start with P)")

    surname, _, given = line1[5:].partition(_FILLER * 2)
    personal = line2[28:42]
    personal_ok = (
        line2[42] in (_FILLER, "0") if set(personal) == {_FILLER} else _digit_ok(personal, line2[42])
    )
    composite_src = line2[0:10] + line2[13:20] + line2[21:43]
    checks = {
        "document_number": _digit_ok(line2[0:9], line2[9]),
        "birth_date": _digit_ok(line2[13:19], line2[19]),
        "expiry_date": _digit_ok(line2[21:27], line2[27]),
        "personal_number": personal_ok,
        "composite": _digit_ok(composite_src, line2[43]),
    }
    return TD3(
        issuer=line1[2:5].strip(_FILLER),
        surname=surname.replace(_FILLER, " ").strip(),
        given_names=given.replace(_FILLER, " ").strip(),
        document_number=line2[0:9].strip(_FILLER),
        nationality=line2[10:13].strip(_FILLER),
        birth_date=line2[13:19],
        sex=line2[20],
        expiry_date=line2[21:27],
        personal_number=personal.strip(_FILLER),
        checks=checks,
    )


# OCR confusions, applied only where the MRZ field type is known.
_TO_DIGIT = str.maketrans("OQDILZSBG", "000112586")
_TO_ALPHA = str.maketrans("012568", "OIZSGB")
_NUMERIC_LINE2 = frozenset({9, *range(13, 20), *range(21, 28), 42, 43})


def _fit(line: str) -> str:
    if not isinstance(line, str):
        raise ValueError("MRZ lines must be strings")
    cleaned = re.sub(r"[^A-Z0-9<]", _FILLER, re.sub(r"\s+", "", line.upper()))
    return cleaned.ljust(_LINE_LEN, _FILLER)[:_LINE_LEN]


def _map_positions(line: str, positions, table) -> str:
    return "".join(c.translate(table) if i in positions else c for i, c in enumerate(line))


def normalize_td3(line1: str, line2: str) -> tuple[str, str]:
    """Repair typical OCR noise (O/0, Q/0, « for <, dropped fillers) using field types.

    Never touches the alphanumeric document and personal numbers, so a genuinely
    wrong value still fails its check digit afterwards.
    """
    fixed1 = _map_positions(_fit(line1), range(2, _LINE_LEN), _TO_ALPHA)
    fixed2 = _map_positions(_fit(line2), _NUMERIC_LINE2, _TO_DIGIT)
    fixed2 = _map_positions(fixed2, range(10, 13), _TO_ALPHA)
    return fixed1, fixed2


def parse_td3_ocr(line1: str, line2: str) -> TD3:
    return parse_td3(*normalize_td3(line1, line2))


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def is_valid_for_months(expiry_date: str, today: date, months: int = 6) -> bool:
    """True if the passport is valid for at least `months` more months. Bad dates are invalid."""
    try:
        expiry = date(2000 + int(expiry_date[0:2]), int(expiry_date[2:4]), int(expiry_date[4:6]))
    except ValueError:
        return False
    return expiry >= _add_months(today, months)


def birth_to_date(birth_date: str, today: date) -> date:
    """Expand a YYMMDD birth date; a result in the future belongs to the 1900s."""
    yy, mm, dd = int(birth_date[0:2]), int(birth_date[2:4]), int(birth_date[4:6])
    candidate = date(2000 + yy, mm, dd)
    return candidate if candidate <= today else date(1900 + yy, mm, dd)
