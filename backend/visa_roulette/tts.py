"""Local text to speech through macOS `say`, returned as WAV so the browser can route it through an AnalyserNode."""

import re
import subprocess
import tempfile
from pathlib import Path

VOICES = {"en-gb": "Daniel", "en-au": "Karen", "en-us": "Samantha", "en-neutral": "Samantha", "en-sg": "Rishi", "en-gulf": "Rishi"}
DEFAULT_VOICE = "Samantha"
MAX_TEXT = 600
TIMEOUT_S = 20
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


class TtsUnavailable(Exception):
    """`say` or `afconvert` is missing or failed."""


def voice_for(key: str) -> str:
    return VOICES.get(key, DEFAULT_VOICE)


def clean(text: str) -> str:
    return " ".join(_CONTROL.sub(" ", text).split())[:MAX_TEXT]


def synthesize(text: str, voice_key: str) -> bytes:
    spoken = clean(text)
    with tempfile.TemporaryDirectory() as tmp:
        aiff, wav = Path(tmp, "s.aiff"), Path(tmp, "s.wav")
        try:
            subprocess.run(["say", "-v", voice_for(voice_key), "-o", str(aiff), "--", spoken], check=True, timeout=TIMEOUT_S, capture_output=True)
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@22050", "-c", "1", str(aiff), str(wav)], check=True, timeout=TIMEOUT_S, capture_output=True)
        except (OSError, subprocess.SubprocessError) as err:
            raise TtsUnavailable("speech synthesis failed") from err
        return wav.read_bytes()
