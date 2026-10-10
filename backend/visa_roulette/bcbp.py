"""IATA BCBP (Bar Coded Boarding Pass) mandatory block: build and parse."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from visa_roulette.text import ascii_upper

_MANDATORY_LEN = 60


@dataclass(frozen=True)
class BoardingPass:
    surname: str
    given_names: str
    pnr: str
    origin: str
    destination: str
    carrier: str
    flight: str
    flight_date: date
    cabin: str
    seat: str
    sequence: str


def _field(name: str, value: str, pattern: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError(f"invalid {name}: {value!r}")
    return value


def _name_field(surname: str, given_names: str) -> str:
    def letters(text: str) -> str:
        return re.sub(r"[^A-Z ]", "", ascii_upper(text))

    return f"{letters(surname)}/{letters(given_names)}"[:20].ljust(20)


def build_bcbp(bp: BoardingPass) -> str:
    pnr = _field("pnr", bp.pnr, r"[A-Z0-9]{1,7}")
    origin = _field("origin", bp.origin, r"[A-Z]{3}")
    destination = _field("destination", bp.destination, r"[A-Z]{3}")
    carrier = _field("carrier", bp.carrier, r"[A-Z0-9]{1,3}")
    flight = _field("flight", bp.flight, r"[A-Z0-9]{1,5}")
    cabin = _field("cabin", bp.cabin, r"[A-Z]")
    seat = _field("seat", bp.seat, r"[A-Z0-9]{1,4}")
    sequence = _field("sequence", bp.sequence, r"[A-Z0-9]{1,5}")
    day_of_year = bp.flight_date.timetuple().tm_yday
    return (
        "M1"
        f"{_name_field(bp.surname, bp.given_names)}"
        "E"
        f"{pnr:<7}"
        f"{origin}{destination}"
        f"{carrier:<3}{flight:<5}"
        f"{day_of_year:03d}"
        f"{cabin}"
        f"{seat:<4}"
        f"{sequence:<5}"
        "1"
        "00"
    )


def _day_of_year(raw: str, year: int) -> int:
    if not re.fullmatch(r"[0-9]{3}", raw):
        raise ValueError(f"invalid day of year: {raw!r}")
    day = int(raw)
    max_day = 366 if calendar.isleap(year) else 365
    if not 1 <= day <= max_day:
        raise ValueError(f"day of year {day} out of range for {year}")
    return day


def parse_bcbp(data: str, year: int) -> BoardingPass:
    if not isinstance(data, str) or len(data) < _MANDATORY_LEN or not data.startswith("M"):
        raise ValueError("not a BCBP boarding pass")
    if not 1900 <= year <= 2100:
        raise ValueError(f"unreasonable year: {year}")
    surname, _, given = data[2:22].strip().partition("/")
    day = _day_of_year(data[44:47], year)
    return BoardingPass(
        surname=surname,
        given_names=given,
        pnr=data[23:30].strip(),
        origin=data[30:33],
        destination=data[33:36],
        carrier=data[36:39].strip(),
        flight=data[39:44].strip(),
        flight_date=date(year, 1, 1) + timedelta(days=day - 1),
        cabin=data[47],
        seat=data[48:52].strip(),
        sequence=data[52:57].strip(),
    )
