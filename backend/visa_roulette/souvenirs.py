"""Souvenir chips: leave a note about where you landed, take home a stranger's.

Only a first name or nickname, two countries and a short note are kept, on the booth laptop. No passport data.
Cold start: a few clearly labelled seeded travellers, so the very first visitor still gets a stranger.
"""

import json
import os
import random
import re
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SEED_PATH = DATA_DIR / "souvenir_seed.json"
JOURNAL_PATH = Path(os.environ.get("VISA_ROULETTE_JOURNAL", DATA_DIR / "souvenirs.jsonl"))
DEFAULT_NICKNAME = "A traveller"
DEFAULT_NOTE = "No note. Just vibes."
MAX_NICKNAME = 20
MAX_NOTE = 80
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_BLOCKED_STEMS = ("fuck", "shit", "bitch", "cunt", "dick", "cock", "pussy", "whore", "slut", "nigg", "fag", "rape", "nazi", "asshole", "bastard", "wank", "twat", "porn")
_LEET = str.maketrans("01345$@!", "oieassai")
_WORD = re.compile(r"[a-z]+")


def _blocked(text: str) -> bool:
    """Word-prefix match, so Scunthorpe passes. Runs of single letters ("f u c k", "b.i.t.c.h") are rejoined first."""
    words, run = [], ""
    for token in _WORD.findall(text.lower().translate(_LEET)):
        if len(token) == 1:
            run += token
            continue
        words.extend(filter(None, (run, token)))
        run = ""
    words.extend(filter(None, (run,)))
    return any(word.startswith(stem) for word in words for stem in _BLOCKED_STEMS)


def clean(text: str | None, limit: int, fallback: str) -> str:
    """Plain text only: control characters become spaces, runs of spaces collapse, length is capped, rude words fall back."""
    squashed = " ".join(_CONTROL.sub(" ", text or "").split())[:limit].strip()
    return fallback if not squashed or _blocked(squashed) else squashed


class Souvenir(BaseModel):
    model_config = ConfigDict(frozen=True)

    origin: str = Field(pattern=r"^[A-Z]{3}$")
    landing_iso3: str = Field(pattern=r"^[A-Z]{3}$")
    nickname: str = Field(max_length=MAX_NICKNAME)
    note: str = Field(max_length=MAX_NOTE)
    seeded: bool = False
    nationality: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    status: str | None = Field(default=None, max_length=16)
    for_you_status: str | None = Field(default=None, max_length=16)
    for_you_label: str | None = Field(default=None, max_length=40)


class Journal:
    """Append-only JSON lines. A damaged line is skipped, never fatal."""

    def __init__(self, path: Path, seed_path: Path = SEED_PATH, rng: random.Random | None = None) -> None:
        self.path = path
        self.seed_path = seed_path
        self.rng = rng or random.Random()
        self._lock = threading.Lock()

    def _load(self, path: Path, seeded: bool) -> list:
        if not path.exists():
            return []
        text = path.read_text()
        rows = json.loads(text) if path.suffix == ".json" else [self._line(line) for line in text.splitlines()]
        out = []
        for row in rows:
            try:
                out.append(Souvenir.model_validate({**(row or {}), "seeded": seeded}))
            except ValueError:
                continue
        return out

    @staticmethod
    def _line(line: str):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def all(self) -> list:
        return self._load(self.seed_path, True) + self._load(self.path, False)

    def swap(self, mine: Souvenir) -> Souvenir | None:
        """Keep `mine`, hand back a stranger's. Prefers a different landing country and never returns your own."""
        with self._lock:
            known = self.all()
            key = (mine.origin, mine.landing_iso3, mine.nickname, mine.note)
            if not any((s.origin, s.landing_iso3, s.nickname, s.note) == key and not s.seeded for s in known):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a") as handle:
                    handle.write(json.dumps(mine.model_dump(exclude={"seeded", "for_you_status", "for_you_label"}), separators=(",", ":")) + "\n")
            others = [s for s in known if (s.origin, s.landing_iso3, s.nickname, s.note) != key]
            fresh = [s for s in others if s.landing_iso3 != mine.landing_iso3]
            pool = fresh or others
            return self.rng.choice(pool) if pool else None
