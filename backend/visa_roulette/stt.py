"""Local speech to text (faster-whisper). Audio never leaves the machine."""

import io
import os
from functools import lru_cache

MODEL_NAME = os.environ.get("VISA_ROULETTE_STT_MODEL", "base.en")
MAX_BYTES = 2_000_000


class SttError(Exception):
    """The audio could not be transcribed."""


class SttUnavailable(SttError):
    """faster-whisper is not installed."""


@lru_cache(maxsize=1)
def _model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as err:
        raise SttUnavailable("faster-whisper is not installed") from err
    return WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")


def warm() -> bool:
    try:
        _model()
    except (SttError, OSError):
        return False
    return True


def transcribe(data: bytes, model=None) -> str:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("audio is empty or too large")
    try:
        segments, _ = (model or _model()).transcribe(io.BytesIO(data), language="en", beam_size=1, vad_filter=False)
        return " ".join(segment.text.strip() for segment in segments).strip()
    except SttError:
        raise
    except Exception as err:
        raise SttError("could not read that audio") from err
