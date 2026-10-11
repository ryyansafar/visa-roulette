"""Vercel entrypoint: the booth API without the hardware.

Vercel serves web/, assets/ and fixtures/ from its CDN (see scripts/vercel_build.sh); this function only answers /api/*.
Heavy or booth-only pieces (OCR, camera, ESP32 websockets, local model, speech) degrade to clear 503s or rule-based
answers instead of failing at import time.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("VISA_ROULETTE_HOSTED", "1")
os.environ.setdefault("VISA_ROULETTE_JOURNAL", "/tmp/visa_roulette_souvenirs.jsonl")  # the bundle is read-only, /tmp is not

from visa_roulette.api import create_app  # noqa: E402

app = create_app(hosted_mode=True)
