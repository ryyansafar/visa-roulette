#!/usr/bin/env python3
"""Fetch things-to-see and one photo for every country the globe can land on.

Sources (all open, citable):
  * Wikivoyage country article: the Cities / Other destinations lists and "See" listings pick the sights.
  * Wikipedia (REST/Action API) article of each sight: a short descriptive sentence and the lead image.
  * Wikimedia Commons file metadata: author and licence; only CC0, public domain, CC BY and CC BY-SA are kept.

Output (idempotent; re-running skips countries already done unless --force):
  rules/destinations.json         country entry: highlights[{title, blurb}], season, tip, source, sources[], photo{subject}
  assets/places/<ISO3>-1.jpg      one landscape photo, max 1400 px wide, JPEG ~80, <= ~250 KB
  assets/places/credits.json      "<ISO3>-1": {title, author, license, source, subject}

The 11 hand-curated countries are never touched. Countries with no acceptable photo or sights are skipped
and listed at the end; nothing is invented. Text is taken from the fetched source text (Wikivoyage / Wikipedia,
CC BY-SA); blurbs are single shortened sentences with markup removed and the source listed beside them.

Usage: .venv/bin/python scripts/fetch_places.py [--only FJI,KEN] [--force] [--limit N] [--cache DIR]
"""

import argparse
import hashlib
import html
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402
from visa_roulette import geo  # noqa: E402

PLACES = ROOT / "assets" / "places"
CREDITS = PLACES / "credits.json"
DESTINATIONS = ROOT / "rules" / "destinations.json"

USER_AGENT = "VisaRoulette/1.0 (hackathon booth; ryyansafar.site)"
AS_OF = "2026-10-11"
NOTE = (
    "Highlights are shortened from Wikivoyage and Wikipedia text (CC BY-SA 4.0), with the source pages listed per country; "
    "the first eleven countries are hand-written booth copy. Unverified, no prices or dates; check the source before travelling."
)
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"

CURATED = {"ARE", "THA", "SGP", "JPN", "GBR", "USA", "FRA", "DEU", "AUS", "MYS", "RUS"}
# Wikivoyage article titles where the map name differs from the article title.
WIKIVOYAGE_TITLE = {
    "BIH": "Bosnia and Herzegovina", "CAF": "Central African Republic", "COG": "Republic of the Congo",
    "COD": "Democratic Republic of the Congo", "DOM": "Dominican Republic", "GNQ": "Equatorial Guinea",
    "FLK": "Falkland Islands", "ATF": "French Southern and Antarctic Lands", "CIV": "Ivory Coast", "SWZ": "Eswatini",
    "SLB": "Solomon Islands", "SDS": "South Sudan", "SAH": "Western Sahara", "PSX": "Palestinian territories",
    "CZE": "Czech Republic", "TLS": "East Timor", "CYN": "Northern Cyprus", "GEO": "Georgia (country)",
    "GMB": "The Gambia", "BHS": "The Bahamas", "KOR": "South Korea", "MKD": "North Macedonia", "USA": "United States of America",
    "TTO": "Trinidad and Tobago", "MMR": "Myanmar", "TUR": "Turkey", "NCL": "New Caledonia", "PRI": "Puerto Rico",
}
SKIP_WORDS = re.compile(
    r"flag|map|logo|coat[_ ]of|arms|seal|emblem|locator|portrait|signature|symbol|diagram|chart|banner|stamp|"
    r"president|king|queen|prime[_ ]minister|statue of|poster|cartoon|icon|montage|collage",
    re.I,
)
LICENCE_OK = re.compile(r"^(CC0\b.*|Public domain.*|PD\b.*|CC[ -]BY(-SA)? \d\.\d(\b.*)?|CC[ -]BY(-SA)? \d\.\d)$", re.I)
LICENCE_BAD = re.compile(r"\b(NC|ND)\b|GFDL|fair use|non-?commercial", re.I)
MIN_WIDTH = 1200
OUT_WIDTH = 1400
MAX_BYTES = 250 * 1024
SLEEP = 0.3
MAX_SIGHT_CANDIDATES = 14


class Http:
    """Polite JSON/bytes fetcher: User-Agent, delay between calls, retries with backoff, optional disk cache."""

    def __init__(self, cache_dir=None):
        self.cache = Path(cache_dir) if cache_dir else None
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)

    def _fetch(self, url: str, tries: int = 6) -> bytes:
        for attempt in range(tries):
            time.sleep(SLEEP)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(req, timeout=40) as resp:
                    return resp.read()
            except urllib.error.HTTPError as err:
                if err.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                    retry_after = err.headers.get("Retry-After", "")
                    time.sleep(min(90, int(retry_after) if retry_after.isdigit() else 10 * (attempt + 1)))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == tries - 1:
                    raise
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError("unreachable")

    def get(self, url: str) -> bytes:
        if not self.cache:
            return self._fetch(url)
        path = self.cache / hashlib.sha1(url.encode()).hexdigest()
        if path.exists():
            return path.read_bytes()
        data = self._fetch(url)
        path.write_bytes(data)
        return data

    def api(self, base: str, **params) -> dict:
        params.setdefault("format", "json")
        params.setdefault("formatversion", "2")
        return json.loads(self.get(f"{base}?{urllib.parse.urlencode(params)}"))


def wiki_url(host: str, title: str) -> str:
    """Readable page URL (non-ASCII kept, only characters that break a URL escaped)."""
    safe = title.replace(" ", "_")
    for ch, enc in (("%", "%25"), ("?", "%3F"), ("#", "%23"), ('"', "%22"), ("<", "%3C"), (">", "%3E")):
        safe = safe.replace(ch, enc)
    return f"https://{host}/wiki/{safe}"


# ---------------------------------------------------------------- Wikivoyage parsing


def clean_markup(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|<!--.*?-->|<[^>]+>", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\([^()]*\)", "", text)  # parentheticals: pronunciations, notes
    text = html.unescape(text).replace("\u00a0", " ")
    text = re.sub(r"\[[^\]]*\]|[\[\]]", "", text)  # bracketed IPA / stray brackets
    text = re.sub(r"\s+", " ", text).strip(" \t-—–―:;,")
    return re.sub(r"^(?:[-—–―]\s*)+", "", text)


def parse_marker_params(raw: str) -> dict:
    out = {}
    raw = re.sub(r"\[\[([^\]]*)\]\]", lambda m: "[[" + m.group(1).replace("|", "\x00") + "]]", raw)  # keep [[A|B]] intact
    for part in raw.split("|"):
        if "=" in part:
            key, _, value = part.partition("=")
            out[key.strip().lower()] = value.strip().replace("\x00", "|")
    return out


def link_target(text: str) -> tuple:
    """(display, wikivoyage page) from a name field that may be [[Page|Shown]] or plain."""
    m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", text)
    if m:
        return clean_markup(m.group(2) or m.group(1)), m.group(1).strip()
    plain = clean_markup(text)
    return plain, plain


def sections(wikitext: str) -> list:
    """[(heading, parent level-2 heading, body)]; sub-headings (e.g. === West Bank ===) inherit their parent."""
    parts = re.split(r"^(={2,4})\s*([^=\n]+?)\s*\1\s*$", wikitext, flags=re.M)
    out, parent = [], ""
    for i in range(1, len(parts) - 2, 3):
        level, heading = len(parts[i]), parts[i + 1].strip()
        if level == 2:
            parent = heading
        out.append((heading, parent, parts[i + 2]))
    return out


def list_candidates(body: str, kind: str) -> list:
    found = []
    for line in body.splitlines():
        if not line.startswith("*"):
            continue
        marker = re.match(r"^\*+\s*\{\{\s*marker\s*\|([^{}]*)\}\}(.*)$", line, flags=re.I)
        if marker:
            params = parse_marker_params(marker.group(1))
            display, page = link_target(params.get("name", ""))
            desc = marker.group(2)
            qid = params.get("wikidata", "")
        else:
            link = re.match(r"^\*+\s*(\[\[[^\]]+\]\])(.*)$", line)
            if not link:
                continue
            display, page = link_target(link.group(1))
            desc, qid = link.group(2), ""
        if display:
            found.append({"title": display, "wv_page": page, "qid": qid if re.fullmatch(r"Q\d+", qid) else "", "desc": clean_markup(desc), "kind": kind})
    for m in re.finditer(r"\{\{\s*listing\s*\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", body, flags=re.I | re.S):
        params = parse_marker_params(re.sub(r"\{\{[^{}]*\}\}", "", m.group(1)).replace("\n", ""))
        display, page = link_target(params.get("name", ""))
        qid = params.get("wikidata", "")
        if display:
            found.append({"title": display, "wv_page": page, "qid": qid if re.fullmatch(r"Q\d+", qid) else "", "desc": clean_markup(params.get("content", "")), "kind": kind})
    return found


def see_candidates(body: str) -> list:
    found = []
    for m in re.finditer(r"\{\{(?:see|do)\s*\|((?:[^{}]|\{\{[^{}]*\}\})*)\}\}", body, flags=re.I | re.S):
        raw = m.group(1)
        params = parse_marker_params(re.sub(r"\{\{[^{}]*\}\}", "", raw))
        name = clean_markup(params.get("name", ""))
        qid = params.get("wikidata", "")
        if name and re.fullmatch(r"Q\d+", qid):
            found.append({"title": name, "wv_page": name, "qid": qid, "desc": clean_markup(params.get("content", "")), "kind": "see"})
    return found


def region_candidates(wikitext: str) -> list:
    """Fallback for articles whose Regionlist names the highlights in prose: [[links]] inside regionNdescription
    (then regionNname / regionNitems when the descriptions give too few)."""
    found = []
    for fields in ("description", "name|items"):
        for m in re.finditer(rf"^\|\s*region\d+(?:{fields})\s*=(.*)$", wikitext, flags=re.M | re.I):
            for link in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", m.group(1)):
                page = link.group(1).strip()
                found.append({"title": page, "wv_page": page, "qid": "", "desc": "", "kind": "region"})
        if len({c["title"] for c in found}) >= 3:
            break
    return found


def gather_candidates(wikitext: str) -> list:
    cities, others, sees = [], [], []
    for heading, parent, body in sections(wikitext):
        h = heading.lower()
        if parent.lower() != h and parent.lower() in ("cities", "other destinations", "destinations", "islands", "settlements"):
            h = parent.lower()
        if h == "see":
            sees += see_candidates(body)
        elif "other destinations" in h or h == "destinations" or "top destinations" in h:
            others += list_candidates(body, "destination")
        elif h in ("cities", "towns", "cities and towns", "islands", "settlements", "national parks") or h.startswith("cities"):
            cities += list_candidates(body, "city")
    merged, seen = [], set()
    pools = [cities, others]
    for i in range(max(len(cities), len(others))):
        for pool in pools:
            if i < len(pool):
                merged.append(pool[i])
    merged += sees
    if not merged:
        merged = region_candidates(wikitext)
    unique = []
    for cand in merged:
        key = cand["title"].lower()
        if key not in seen and not re.search(r"\d", cand["title"]):
            seen.add(key)
            unique.append(cand)
    return unique[:MAX_SIGHT_CANDIDATES]


# ---------------------------------------------------------------- Wikipedia / Wikidata lookups


def resolve_qids(http: Http, cands: list) -> None:
    """Fill in missing Wikidata ids from Wikivoyage page properties (safer than guessing Wikipedia titles)."""
    missing = [c for c in cands if not c["qid"]]
    for i in range(0, len(missing), 40):
        chunk = missing[i : i + 40]
        data = http.api(WIKIVOYAGE_API, action="query", titles="|".join(c["wv_page"] for c in chunk), prop="pageprops", ppprop="wikibase_item", redirects=1)
        query = data.get("query", {})
        alias = {}
        for kind in ("normalized", "redirects"):
            for r in query.get(kind, []):
                alias[r["from"]] = r["to"]
        qid_by_title = {p["title"]: p.get("pageprops", {}).get("wikibase_item", "") for p in query.get("pages", [])}
        for c in chunk:
            title = c["wv_page"]
            for _ in range(3):
                title = alias.get(title, title)
            c["qid"] = qid_by_title.get(title, "")


def enwiki_titles(http: Http, qids: list) -> dict:
    out = {}
    for i in range(0, len(qids), 40):
        data = http.api(WIKIDATA_API, action="wbgetentities", ids="|".join(qids[i : i + 40]), props="sitelinks", sitefilter="enwiki")
        for qid, ent in data.get("entities", {}).items():
            link = ent.get("sitelinks", {}).get("enwiki")
            if link:
                out[qid] = link["title"]
    return out


def wikipedia_pages(http: Http, titles: list) -> dict:
    pages = {}
    for i in range(0, len(titles), 20):
        data = http.api(
            WIKIPEDIA_API, action="query", titles="|".join(titles[i : i + 20]), redirects=1,
            prop="pageimages|extracts|description", piprop="original|name", exintro=1, explaintext=1, exlimit="max",
        )
        for p in data.get("query", {}).get("pages", []):
            if not p.get("missing"):
                pages[p["title"]] = p
    return pages


def file_info(http: Http, filename: str) -> dict | None:
    data = http.api(
        WIKIPEDIA_API, action="query", titles=f"File:{filename}", prop="imageinfo",
        iiprop="extmetadata|size|mime|url", iiurlwidth=OUT_WIDTH, redirects=1,
    )
    pages = data.get("query", {}).get("pages", [])
    info = (pages[0].get("imageinfo") or [None])[0] if pages else None
    if not info:
        return None
    meta = info.get("extmetadata", {})
    plain = lambda key: clean_markup(re.sub(r"<[^>]+>", "", meta.get(key, {}).get("value", "")))  # noqa: E731
    return {
        "title": pages[0]["title"].removeprefix("File:"),
        "width": info["width"], "height": info["height"], "mime": info.get("mime", ""),
        "thumb": info.get("thumburl") or info["url"],
        "license": plain("LicenseShortName") or plain("License"),
        "author": plain("Artist") or plain("Credit"),
        "restrictions": plain("Restrictions"),
        "page": info.get("descriptionurl") or wiki_url("commons.wikimedia.org", "File:" + filename),
    }


def photo_acceptable(info: dict | None, filename: str) -> bool:
    if not info or info["mime"] != "image/jpeg" or SKIP_WORDS.search(filename) or not info["author"]:
        return False
    if info["width"] < MIN_WIDTH or info["width"] < info["height"] * 1.2:
        return False
    licence = info["license"]
    if LICENCE_BAD.search(licence) or not LICENCE_OK.match(licence):
        return False
    return "personality" not in info["restrictions"].lower()


# ---------------------------------------------------------------- blurbs


ABBREV = re.compile(r"\b(?:lit|c|ca|approx|St|Mt|Mr|Mrs|Dr|vs|etc|e\.g|i\.e|No|Fr)\.$")


def sentences(text: str) -> list:
    text = html.unescape(text)
    text = re.sub(r"\([^()]*\)|\[[^\]]*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    out, buf = [], ""
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text):
        buf = f"{buf} {part}".strip() if buf else part
        if not ABBREV.search(buf):
            out.append(buf)
            buf = ""
    return out + ([buf] if buf else [])


NON_LATIN = re.compile(r"[^\x00-\u024f\u2010-\u2027\u2030-\u205e]")
DANGLING = re.compile(r"(?:\b(?:a|an|the|and|or|of|to|in|with|is|are|was|by|for)|,|;|:)\.?$", re.I)


def clean_enough(sentence: str) -> bool:
    """Reject text that is not plain, complete English prose."""
    if NON_LATIN.search(sentence) or re.search(r"[\[\]{}<>|&]|&\w+;", sentence):
        return False
    if re.search(r"(?:\b(?:a|an|and|or|of|to|the)|,)\s*[,.]|\b(?:a|an),", sentence):
        return False
    return not DANGLING.search(sentence.strip())


def tidy_sentence(text: str) -> str:
    text = re.sub(r"\s+([,.;:])", r"\1", text.strip())
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


def shorten(sentence: str, limit: int = 130) -> str:
    """Keep blurbs short: cut a long sentence at its last clause break before `limit` (never mid-clause)."""
    if len(sentence) <= limit:
        return sentence
    cut = max(sentence.rfind("; ", 0, limit), sentence.rfind(", ", 0, limit), sentence.rfind(" with ", 0, limit), sentence.rfind(" and ", 0, limit))
    return sentence[:cut].rstrip(" ,;") + "." if cut >= 40 else sentence


def usable(sentence: str, low: int, high: int) -> bool:
    return low <= len(sentence) <= high and not re.search(r"\d", sentence) and "=" not in sentence and clean_enough(sentence)


def make_blurb(cand: dict, page: dict | None) -> str:
    """One sentence, digit-free, from the Wikivoyage listing text if present, else the Wikipedia lead."""
    listing = tidy_sentence(cand["desc"]) if cand["desc"] else ""
    if listing and usable(listing, 20, 200):
        short = shorten(listing)
        if usable(short, 20, 200):
            return short
    if page:
        for sentence in sentences(page.get("extract", ""))[:4]:
            if usable(sentence, 30, 220):
                short = shorten(tidy_sentence(sentence))
                if usable(short, 30, 200):
                    return short
    return ""


# ---------------------------------------------------------------- image saving


def save_jpeg(raw: bytes, dest: Path) -> int:
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    width = OUT_WIDTH
    while True:
        frame = image if image.width <= width else image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        for quality in (80, 74, 68, 62, 56):
            buf = io.BytesIO()
            frame.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
            if buf.tell() <= MAX_BYTES:
                dest.write_bytes(buf.getvalue())
                return buf.tell()
        width = int(width * 0.88)
        if width < 800:
            dest.write_bytes(buf.getvalue())
            return buf.tell()


# ---------------------------------------------------------------- per country


def build_country(http: Http, iso3: str, dry_run: bool = False) -> tuple:
    """Return (entry, credit) or raise LookupError with the reason it was skipped."""
    name = geo.country_name(iso3)
    wv_title = WIKIVOYAGE_TITLE.get(iso3, name)
    data = http.api(WIKIVOYAGE_API, action="parse", page=wv_title, prop="wikitext", redirects=1)
    if "parse" not in data:
        raise LookupError(f"no Wikivoyage article '{wv_title}'")
    wikitext = data["parse"]["wikitext"]
    page_title = data["parse"]["title"]
    cands = gather_candidates(wikitext)
    if not cands:
        raise LookupError("no destination lists on Wikivoyage article")
    resolve_qids(http, cands)
    titles = enwiki_titles(http, sorted({c["qid"] for c in cands if c["qid"]}))
    pages = wikipedia_pages(http, sorted(set(titles.values())))
    for cand in cands:
        cand["wp_title"] = titles.get(cand["qid"], "")
        cand["page"] = pages.get(cand["wp_title"]) if cand["wp_title"] else None
        cand["blurb"] = make_blurb(cand, cand["page"])
    cands = [c for c in cands if c["blurb"] and c["wp_title"]]
    if len(cands) < 3:
        raise LookupError(f"only {len(cands)} sights with source text")

    photo = None
    for cand in cands:
        original = (cand["page"] or {}).get("original")
        filename = (cand["page"] or {}).get("pageimage", "")
        if not original or not filename or original["width"] < MIN_WIDTH or SKIP_WORDS.search(filename):
            continue
        info = file_info(http, filename)
        if photo_acceptable(info, filename):
            photo = (cand, info)
            break
    if not photo:
        raise LookupError("no acceptable open-licensed landscape photo on any sight page")
    lead, info = photo
    chosen = [lead] + [c for c in cands if c is not lead][:2]
    sources = [wiki_url("en.wikivoyage.org", page_title)] + [wiki_url("en.wikipedia.org", c["wp_title"]) for c in chosen]
    entry = {
        "highlights": [{"title": c["title"], "blurb": c["blurb"]} for c in chosen],
        "season": None, "tip": None,
        "source": sources[0], "sources": sources,
        "photo": {"subject": lead["title"]},
    }
    if re.search(r"\d", json.dumps(entry, ensure_ascii=False).replace("https://", "")):
        raise LookupError("digits in assembled copy")
    credit = {"title": info["title"], "author": info["author"], "license": info["license"], "source": info["page"], "subject": lead["title"]}
    if not dry_run:
        size = save_jpeg(http.get(info["thumb"]), PLACES / f"{iso3}-1.jpg")
        print(f"  {iso3} {name}: {lead['title']} ({info['license']}, {size // 1024} KB)")
    return entry, credit


def dump_destinations(data: dict) -> str:
    lines = [
        "{",
        f'  "note": {json.dumps(data["note"], ensure_ascii=False)},',
        f'  "as_of": {json.dumps(data["as_of"])},',
        '  "destinations": {',
    ]
    items = list(data["destinations"].items())
    for i, (iso3, entry) in enumerate(items):
        lines.append(f'    "{iso3}": {json.dumps(entry, ensure_ascii=False)}{"," if i < len(items) - 1 else ""}')
    lines += ["  }", "}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated ISO3 codes")
    ap.add_argument("--force", action="store_true", help="refetch countries that already have a generated entry")
    ap.add_argument("--limit", type=int, help="stop after N countries (testing)")
    ap.add_argument("--cache", help="directory to cache API responses (development)")
    args = ap.parse_args()

    http = Http(args.cache)
    PLACES.mkdir(parents=True, exist_ok=True)
    destinations = json.loads(DESTINATIONS.read_text())
    credits = json.loads(CREDITS.read_text())
    wanted = [c.iso3 for c in geo.countries() if c.iso3 not in CURATED]
    if args.only:
        only = {x.strip().upper() for x in args.only.split(",")}
        wanted = [c for c in wanted if c in only]
    if args.limit:
        wanted = wanted[: args.limit]

    skipped, done = [], 0
    for iso3 in wanted:
        entry_exists = iso3 in destinations["destinations"] and (PLACES / f"{iso3}-1.jpg").exists()
        if entry_exists and not args.force:
            continue
        try:
            entry, credit = build_country(http, iso3)
        except LookupError as err:
            skipped.append((iso3, geo.country_name(iso3), str(err)))
            print(f"  SKIP {iso3} {geo.country_name(iso3)}: {err}")
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, ValueError, OSError) as err:
            skipped.append((iso3, geo.country_name(iso3), f"{type(err).__name__}: {err}"))
            print(f"  SKIP {iso3} {geo.country_name(iso3)}: {type(err).__name__}: {err}")
            continue
        destinations["destinations"][iso3] = entry
        credits[f"{iso3}-1"] = credit
        done += 1
        # persist as we go so an interrupted run keeps its progress
        destinations["note"], destinations["as_of"] = NOTE, AS_OF
        DESTINATIONS.write_text(dump_destinations(destinations))
        CREDITS.write_text(json.dumps(credits, indent=2, ensure_ascii=False) + "\n")

    destinations["note"], destinations["as_of"] = NOTE, AS_OF
    DESTINATIONS.write_text(dump_destinations(destinations))
    print(f"\nDone: {done} new/updated, {len(skipped)} skipped.")
    for iso3, name, why in skipped:
        print(f"  skipped {iso3} {name}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
