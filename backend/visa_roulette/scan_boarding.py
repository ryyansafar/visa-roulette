"""Find and decode an IATA boarding-pass barcode (PDF417, QR or Aztec) in an image."""

from dataclasses import dataclass

import zxingcpp
from PIL import Image, ImageOps

from visa_roulette.bcbp import BoardingPass, parse_bcbp
from visa_roulette.errors import ScanError


@dataclass(frozen=True)
class BoardingScan:
    raw: str
    boarding_pass: BoardingPass
    format: str


def _variants(image: Image.Image):
    yield image
    gray = ImageOps.autocontrast(image.convert("L"))
    yield gray
    if gray.width < 1600:
        yield gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)


def scan_boarding_pass(image: Image.Image, year: int) -> BoardingScan:
    for variant in _variants(image):
        for result in zxingcpp.read_barcodes(variant):
            text = result.text
            if len(text) < 60 or not text.startswith("M"):
                continue
            try:
                return BoardingScan(text, parse_bcbp(text, year), result.format.name)
            except ValueError:
                continue
    raise ScanError("no_barcode", "No boarding-pass barcode found. Hold the pass flat and fill the frame.")
