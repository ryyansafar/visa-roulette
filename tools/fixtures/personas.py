"""Fictional traveller personas used for specimen props. None of these are real people."""

from dataclasses import dataclass
from datetime import date

FLIGHT_DATE = date(2026, 10, 11)
RETURN_DATE = date(2026, 10, 16)


@dataclass(frozen=True)
class Persona:
    key: str
    surname: str
    given_names: str
    birth: date
    sex: str
    expiry: date
    doc_no: str
    place_of_birth: str
    seat: str
    story: str
    booking_name: str
    expected: str
    expected_reason: str
    bag: tuple


PERSONAS = (
    Persona(
        key="lakshmi",
        surname="NAIR",
        given_names="LAKSHMI AMMAL",
        birth=date(1964, 3, 5),
        sex="F",
        expiry=date(2027, 3, 10),
        doc_no="Z1234567",
        place_of_birth="KOZHIKODE",
        seat="014A",
        story=(
            "You are Lakshmi Ammal, 62, a retired teacher. This is your first flight. "
            "You are visiting your son in Dubai and packed gifts and your daily tablets."
        ),
        booking_name="LAKSHMI AMMAL NAIR",
        expected="HELD",
        expected_reason="Passport has under 6 months validity left on the travel date.",
        bag=("blood pressure tablets", "banana chips", "dried coconut"),
    ),
    Persona(
        key="arjun",
        surname="MENON",
        given_names="ARJUN",
        birth=date(2002, 7, 14),
        sex="M",
        expiry=date(2033, 8, 15),
        doc_no="Z7654321",
        place_of_birth="KOCHI",
        seat="022C",
        story=(
            "You are Arjun, 24, a developer on a short work trip to Dubai. "
            "Your papers are in order and you travel light."
        ),
        booking_name="ARJUN MENON",
        expected="CLEARED",
        expected_reason="All documents consistent and valid.",
        bag=("laptop", "phone charger"),
    ),
    Persona(
        key="shafeeq",
        surname="MOHAMMED",
        given_names="SHAFEEQ",
        birth=date(1990, 11, 22),
        sex="M",
        expiry=date(2030, 6, 12),
        doc_no="Z2468135",
        place_of_birth="MALAPPURAM",
        seat="031F",
        story=(
            "You are Shafeeq, 35, visiting family in Dubai. You booked your hotel "
            "in a hurry and typed your name a little differently."
        ),
        booking_name="MOHAMED SHAFIQ",
        expected="HELD",
        expected_reason="Name on hotel booking does not match the passport.",
        bag=("clothes", "gifts"),
    ),
)
