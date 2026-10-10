"""IATA BCBP (Bar Coded Boarding Pass) mandatory block: build and parse."""

from dataclasses import dataclass
from datetime import date, timedelta

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


def build_bcbp(bp: BoardingPass) -> str:
    name = f"{bp.surname}/{bp.given_names}".upper()[:20].ljust(20)
    day_of_year = bp.flight_date.timetuple().tm_yday
    return (
        "M1"
        f"{name}"
        "E"
        f"{bp.pnr:<7}"
        f"{bp.origin:<3}{bp.destination:<3}"
        f"{bp.carrier:<3}{bp.flight:<5}"
        f"{day_of_year:03d}"
        f"{bp.cabin}"
        f"{bp.seat:<4}"
        f"{bp.sequence:<5}"
        "1"
        "00"
    )


def parse_bcbp(data: str, year: int) -> BoardingPass:
    if len(data) < _MANDATORY_LEN or not data.startswith("M"):
        raise ValueError("not a BCBP boarding pass")
    surname, _, given = data[2:22].strip().partition("/")
    day_of_year = int(data[44:47])
    return BoardingPass(
        surname=surname,
        given_names=given,
        pnr=data[23:30].strip(),
        origin=data[30:33],
        destination=data[33:36],
        carrier=data[36:39].strip(),
        flight=data[39:44].strip(),
        flight_date=date(year, 1, 1) + timedelta(days=day_of_year - 1),
        cabin=data[47],
        seat=data[48:52].strip(),
        sequence=data[52:57].strip(),
    )
