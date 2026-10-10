"""Draw specimen props (passport page, boarding pass, text cards) with Pillow."""

from datetime import date

from PIL import Image, ImageDraw, ImageFont
from pdf417gen import encode, render_image

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
WATERMARK = ("SPECIMEN", "NOT A REAL DOCUMENT")


def font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def fmt_date(d: date) -> str:
    return d.strftime("%d %b %Y").upper()


def _watermark(base: Image.Image, lines: tuple, region_height: int) -> Image.Image:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    top = region_height // 3
    d.text((120, top), lines[0], font=font(SANS, 120), fill=(180, 30, 30, 60))
    d.text((150, top + 130), lines[1], font=font(SANS, 56), fill=(180, 30, 30, 60))
    rotated = layer.rotate(12, resample=Image.BICUBIC)
    return Image.alpha_composite(base.convert("RGBA"), rotated).convert("RGB")


def _silhouette(d: ImageDraw.ImageDraw, box: tuple) -> None:
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=(205, 205, 205), outline=(120, 120, 120), width=3)
    cx = (x0 + x1) // 2
    d.ellipse((cx - 55, y0 + 50, cx + 55, y0 + 160), fill=(150, 150, 150))
    d.ellipse((cx - 105, y0 + 180, cx + 105, y1 + 90), fill=(150, 150, 150))


def passport_page(p, line1: str, line2: str) -> Image.Image:
    img = Image.new("RGB", (1100, 760), (238, 232, 214))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1100, 90), fill=(28, 44, 84))
    d.text((40, 24), "TRAVEL DOCUMENT  |  SPECIMEN", font=font(SANS, 40), fill="white")
    _silhouette(d, (60, 130, 340, 470))
    rows = (
        ("SURNAME", p.surname),
        ("GIVEN NAMES", p.given_names),
        ("NATIONALITY", "IND"),
        ("DATE OF BIRTH", fmt_date(p.birth)),
        ("SEX", p.sex),
        ("PLACE OF BIRTH", p.place_of_birth),
        ("DATE OF EXPIRY", fmt_date(p.expiry)),
        ("DOCUMENT NO.", p.doc_no),
    )
    for i, (label, value) in enumerate(rows):
        x, y = (380 if i % 2 == 0 else 740), 120 + (i // 2) * 85
        d.text((x, y), label, font=font(SANS, 18), fill=(110, 110, 110))
        d.text((x, y + 24), value, font=font(SANS, 30), fill=(20, 20, 20))
    img = _watermark(img, WATERMARK, 420)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 560, 1100, 760), fill="white")
    mono = font(MONO, 31)
    d.text((40, 600), line1, font=mono, fill="black")
    d.text((40, 650), line2, font=mono, fill="black")
    return img


def barcode_image(data: str, width: int = 980) -> Image.Image:
    codes = encode(data, columns=8, security_level=3)
    img = render_image(codes, scale=4, ratio=3, padding=12).convert("RGB")
    return img.resize((width, int(img.height * width / img.width)), Image.NEAREST)


def boarding_pass(p, bcbp: str, flight_date: date) -> Image.Image:
    img = Image.new("RGB", (1100, 720), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1100, 100), fill=(190, 60, 30))
    d.text((40, 26), "LAYOVER AIR  |  BOARDING PASS (SPECIMEN)", font=font(SANS, 38), fill="white")
    d.text((40, 130), "PASSENGER", font=font(SANS, 18), fill=(110, 110, 110))
    d.text((40, 156), f"{p.surname}/{p.given_names}", font=font(SANS, 40), fill="black")
    d.text((40, 240), "CCJ", font=font(SANS, 110), fill="black")
    d.text((470, 270), "->", font=font(SANS, 70), fill=(190, 60, 30))
    d.text((640, 240), "DXB", font=font(SANS, 110), fill="black")
    d.text((40, 380), "KOZHIKODE", font=font(SANS, 24), fill=(90, 90, 90))
    d.text((640, 380), "DUBAI", font=font(SANS, 24), fill=(90, 90, 90))
    cells = (("FLIGHT", "ZZ 0123"), ("DATE", fmt_date(flight_date)), ("SEAT", p.seat), ("GATE", "4"))
    for i, (label, value) in enumerate(cells):
        x = 40 + i * 260
        d.text((x, 430), label, font=font(SANS, 18), fill=(110, 110, 110))
        d.text((x, 456), value, font=font(SANS, 34), fill="black")
    bar = barcode_image(bcbp)
    img.paste(bar, (60, 530))
    img = _watermark(img, WATERMARK, 700)
    return img


def text_card(title: str, rows: tuple, footer: str = "") -> Image.Image:
    img = Image.new("RGB", (1100, 640), (248, 246, 240))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1100, 90), fill=(40, 90, 70))
    d.text((40, 24), title, font=font(SANS, 38), fill="white")
    for i, (label, value) in enumerate(rows):
        y = 130 + i * 78
        d.text((40, y), label, font=font(SANS, 18), fill=(110, 110, 110))
        d.text((40, y + 24), value, font=font(SANS, 32), fill=(20, 20, 20))
    if footer:
        d.text((40, 590), footer, font=font(SANS, 20), fill=(110, 110, 110))
    return _watermark(img, WATERMARK, 480)
