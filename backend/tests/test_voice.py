import shutil

import pytest
from fastapi.testclient import TestClient

from visa_roulette import officer_flow, stt, tts
from visa_roulette.api import create_app

client = TestClient(create_app())
WAV = b"RIFF" + b"\0" * 400


@pytest.fixture(autouse=True)
def _reset():
    officer_flow.reset()


class FakeModel:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def transcribe(self, source, **kw):
        self.calls += 1
        return iter([type("Seg", (), {"text": self.text})()]), None


def test_transcribe_joins_segments_and_trims():
    assert stt.transcribe(WAV, model=FakeModel("  I am here for tourism.  ")) == "I am here for tourism."


@pytest.mark.parametrize("data", [b"", b"x" * (stt.MAX_BYTES + 1)])
def test_empty_or_oversized_audio_is_rejected(data):
    with pytest.raises(ValueError):
        stt.transcribe(data, model=FakeModel("hi"))


def test_a_model_failure_becomes_a_clean_error():
    class Broken:
        def transcribe(self, *a, **k):
            raise RuntimeError("bad audio")

    with pytest.raises(stt.SttError):
        stt.transcribe(WAV, model=Broken())


def test_listen_endpoint_returns_the_text(monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda data, model=None: "five days")
    res = client.post("/api/officer/listen", content=WAV, headers={"content-type": "audio/wav"})
    assert res.status_code == 200 and res.json() == {"text": "five days"}


def test_listen_can_run_the_interview_turn_in_one_call(monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda data, model=None: "tourism")
    first = client.post("/api/officer/start", json={"nationality": "IND", "destination": "ARE", "visas": []}).json()
    res = client.post(f"/api/officer/listen?session_id={first['session_id']}", content=WAV, headers={"content-type": "audio/wav"})
    body = res.json()
    assert res.status_code == 200 and body["heard"] == "tourism" and body["stage"] == "duration"


def test_listen_with_an_unknown_session_is_a_404(monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda data, model=None: "hi")
    assert client.post("/api/officer/listen?session_id=nope", content=WAV).status_code == 404


def test_listen_rejects_empty_and_oversized_bodies():
    assert client.post("/api/officer/listen", content=b"").status_code == 422
    assert client.post("/api/officer/listen", content=b"x" * (stt.MAX_BYTES + 1)).status_code == 413


def test_listen_when_speech_to_text_is_missing_says_so(monkeypatch):
    def gone(data, model=None):
        raise stt.SttUnavailable("not installed")

    monkeypatch.setattr(stt, "transcribe", gone)
    res = client.post("/api/officer/listen", content=WAV)
    assert res.status_code == 503 and res.json()["detail"]["code"] == "stt_unavailable"


@pytest.mark.parametrize("key,voice", [("en-gb", "Daniel"), ("en-au", "Karen"), ("en-neutral", "Samantha"), ("klingon", "Samantha")])
def test_persona_voices_map_to_installed_macos_voices_with_a_safe_default(key, voice):
    assert tts.voice_for(key) == voice


def test_speak_endpoint_returns_audio(monkeypatch):
    monkeypatch.setattr(tts, "synthesize", lambda text, voice_key: b"RIFFfake")
    res = client.post("/api/officer/speak", json={"text": "Welcome", "voice": "en-gb"})
    assert res.status_code == 200 and res.headers["content-type"] == "audio/wav" and res.content == b"RIFFfake"


def test_speak_rejects_empty_and_overlong_text():
    assert client.post("/api/officer/speak", json={"text": "", "voice": "en-gb"}).status_code == 422
    assert client.post("/api/officer/speak", json={"text": "a" * 601, "voice": "en-gb"}).status_code == 422


def test_speak_strips_control_characters_before_the_shell_sees_them(monkeypatch):
    seen = []
    monkeypatch.setattr(tts, "synthesize", lambda text, voice_key: seen.append(text) or b"RIFF")
    client.post("/api/officer/speak", json={"text": "-v Fred\x00 hello\nworld", "voice": "en-us"})
    assert seen and "\x00" not in seen[0] and "\n" not in seen[0]


@pytest.mark.skipif(not (shutil.which("say") and shutil.which("afconvert")), reason="macOS say/afconvert not available")
def test_real_speech_round_trip_makes_a_wav():
    wav = tts.synthesize("Hello traveller", "en-neutral")
    assert wav[:4] == b"RIFF" and len(wav) > 2000
