"""Generate specimen props: python tools/make_fixtures.py (needs the tools venv)."""

import json
import socket
import sys
import textwrap
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import zxingcpp  # noqa: E402
from visa_roulette.bcbp import BoardingPass, build_bcbp  # noqa: E402
from visa_roulette.mrz import build_td3, parse_td3  # noqa: E402

from tools.fixtures.personas import FLIGHT_DATE, PERSONAS, RETURN_DATE  # noqa: E402
from tools.fixtures.render import boarding_pass, fmt_date, passport_page, text_card  # noqa: E402
from tools.fixtures.wallet import build_wallet  # noqa: E402

OUT = ROOT / "fixtures"


def yymmdd(d: date) -> str:
    return d.strftime("%y%m%d")


def make_boarding_pass(p) -> BoardingPass:
    return BoardingPass(
        surname=p.surname,
        given_names=p.given_names,
        pnr="LAYOV" + p.key[:2].upper(),
        origin="CCJ",
        destination="DXB",
        carrier="ZZ",
        flight="0123",
        flight_date=FLIGHT_DATE,
        cabin="Y",
        seat=p.seat,
        sequence="0007",
    )


def role_card(p):
    story = textwrap.wrap(p.story, 52)[:3]
    rows = [("YOU ARE", f"{p.given_names.title()} {p.surname.title()}")]
    rows += [("SITUATION" if i == 0 else "", line) for i, line in enumerate(story)]
    rows.append(("IN YOUR BAG", ", ".join(p.bag)))
    return text_card("YOUR ROLE  |  SPECIMEN", tuple(rows))


def booking_cards(p):
    ret = text_card(
        "RETURN TICKET  |  SPECIMEN",
        (
            ("PASSENGER", p.booking_name),
            ("ROUTE", "DXB -> CCJ"),
            ("FLIGHT", "ZZ 0124"),
            ("DATE", fmt_date(RETURN_DATE)),
        ),
    )
    hotel = text_card(
        "HOTEL BOOKING  |  SPECIMEN",
        (
            ("GUEST", p.booking_name),
            ("HOTEL", "Desert Palm Suites (fictional)"),
            ("CHECK-IN", fmt_date(FLIGHT_DATE)),
            ("CHECK-OUT", fmt_date(RETURN_DATE)),
        ),
    )
    return ret, hotel


def verify_barcode(img, expected: str) -> None:
    decoded = [r.text for r in zxingcpp.read_barcodes(img)]
    if expected not in decoded:
        raise SystemExit(f"barcode self-check failed: {decoded!r} != {expected!r}")


def build_persona(p) -> dict:
    line1, line2 = build_td3(
        surname=p.surname,
        given_names=p.given_names,
        document_number=p.doc_no,
        nationality="IND",
        birth_date=yymmdd(p.birth),
        sex=p.sex,
        expiry_date=yymmdd(p.expiry),
        issuer="IND",
        personal_number="SPECIMEN",
    )
    if not parse_td3(line1, line2).all_checks_pass:
        raise SystemExit(f"MRZ self-check failed for {p.key}")

    bcbp = build_bcbp(make_boarding_pass(p))
    bp_img = boarding_pass(p, bcbp, FLIGHT_DATE)
    verify_barcode(bp_img, bcbp)

    ret, hotel = booking_cards(p)
    folder = OUT / p.key
    folder.mkdir(parents=True, exist_ok=True)
    images = {
        "passport": passport_page(p, line1, line2),
        "boarding_pass": bp_img,
        "return_ticket": ret,
        "hotel_booking": hotel,
        "role_card": role_card(p),
    }
    for name, img in images.items():
        img.save(folder / f"{name}.png", optimize=True)
    return {
        "key": p.key,
        "mrz": [line1, line2],
        "bcbp": bcbp,
        "booking_name": p.booking_name,
        "expected": p.expected,
        "expected_reason": p.expected_reason,
        "bag": list(p.bag),
        "specimen": True,
    }


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "<your-laptop-ip>"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    manifest = [build_persona(p) for p in PERSONAS]
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT / "wallet.html").write_text(build_wallet(PERSONAS))
    print(f"wrote {len(manifest)} personas to {OUT}")
    print("phone: python3 -m http.server 8000 --directory fixtures --bind 0.0.0.0")
    print(f"then open http://{lan_ip()}:8000/wallet.html on the same Wi-Fi")


if __name__ == "__main__":
    main()
