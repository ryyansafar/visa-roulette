"""Read a passport MRZ from an image: locate, OCR with Tesseract, repair, validate, pick the best."""

import io
import re
import shutil
import subprocess
from dataclasses import dataclass
from itertools import product
from typing import Iterator, Optional

from PIL import Image, ImageOps

from visa_roulette.errors import ScanError
from visa_roulette.mrz import TD3, normalize_td3, parse_td3
from visa_roulette.mrz_locate import locate_mrz

_ALLOWED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")
_WHITELIST = "".join(sorted(_ALLOWED))
_LINE_LEN = 44
_MIN_LINE = 28  # line 1 loses filler glyphs to OCR; _fit pads it back to 44
_MIN_SCORE = 2  # of 5 check digits; below this the read is treated as noise
_OCR_TIMEOUT_S = 25


@dataclass(frozen=True)
class MrzScan:
    line1: str
    line2: str
    td3: TD3
    score: int
    method: str


def ocr_text(image: Image.Image) -> str:
    exe = shutil.which("tesseract")
    if exe is None:
        raise ScanError("ocr_unavailable", "Text recognition (Tesseract) is not installed.", 503)
    gray = ImageOps.autocontrast(image.convert("L"))
    if gray.width < 1600:
        gray = gray.resize((1600, int(gray.height * 1600 / gray.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    gray.save(buffer, "PNG")
    try:
        done = subprocess.run(
            [exe, "stdin", "stdout", "--psm", "6", "-c", f"tessedit_char_whitelist={_WHITELIST}"],
            input=buffer.getvalue(),
            capture_output=True,
            timeout=_OCR_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return ""
    return done.stdout.decode("utf-8", "ignore")


def _candidate_lines(text: str) -> list:
    lines = [re.sub(r"\s+", "", line.upper()) for line in text.splitlines()]
    return [ln for ln in lines if len(ln) >= _MIN_LINE and sum(c in _ALLOWED for c in ln) / len(ln) >= 0.9]


def _line_pairs(lines: list) -> Iterator[tuple]:
    for first, second in zip(lines, lines[1:]):
        if first.startswith("P"):
            yield first, second
    if len(lines) >= 2:
        yield lines[-2], lines[-1]


def _variants(line: str) -> Iterator[str]:
    """The line itself, plus every single-character deletion when OCR inserted one extra glyph."""
    yield line
    if len(line) not in (_LINE_LEN + 1, _LINE_LEN + 2):
        return
    doubled = [i for i in range(len(line)) if line[i] in line[max(i - 1, 0) : i] + line[i + 1 : i + 2]]
    rest = [i for i in range(len(line)) if i not in doubled]
    for i in doubled + rest:  # OCR usually stutters a glyph, so try those deletions first
        yield line[:i] + line[i + 1 :]


def _crops(image: Image.Image) -> Iterator[tuple]:
    located = locate_mrz(image)
    if located is not None:
        yield "localised", located
    for name, share in (("bottom-40", 0.4), ("bottom-25", 0.25)):
        top = int(image.height * (1 - share))
        yield name, image.crop((0, top, image.width, image.height))
    yield "full-frame", image


def read_mrz(image: Image.Image) -> MrzScan:
    best: Optional[MrzScan] = None
    for method, crop in _crops(image):
        for pair in _line_pairs(_candidate_lines(ocr_text(crop))):
            for first, second in product(_variants(pair[0]), _variants(pair[1])):
                try:
                    fixed = normalize_td3(first, second)
                    td3 = parse_td3(*fixed)
                except ValueError:
                    continue
                score = sum(td3.checks.values())
                if best is None or score > best.score:
                    best = MrzScan(fixed[0], fixed[1], td3, score, method)
        if best is not None and best.score == len(best.td3.checks):
            break
    if best is None:
        raise ScanError("no_mrz", "No passport text zone found. Lay the page flat and fill the frame.")
    if best.score < _MIN_SCORE:
        raise ScanError("unreadable_mrz", "The passport text zone was too unclear to read. Try again with less glare.")
    return best
