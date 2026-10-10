"""Routes for the traveller profile, the throw, the landing and the QR hand-off."""

import dataclasses
import json
import re
import secrets
import socket
from collections import OrderedDict
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from visa_roulette import destination as destination_info
from visa_roulette import geo, officer_flow, pick, stt, tts
from visa_roulette import operator as booth_operator
from visa_roulette.camera_throw import throw_from_camera
from visa_roulette.duel import duel
from visa_roulette.errors import ScanError
from visa_roulette.handoff import Handoff, VisaVerdict, encode_handoff, qr_matrix
from visa_roulette.mrz import parse_td3
from visa_roulette.profile import Iso3, TravelerProfile, VisaHeld, prefill_from_mrz
from visa_roulette.souvenirs import (
    DEFAULT_NICKNAME,
    DEFAULT_NOTE,
    JOURNAL_PATH,
    MAX_NICKNAME,
    MAX_NOTE,
    Journal,
    Souvenir,
    clean,
)
from visa_roulette.throw import (
    Sample,
    ThrowDetector,
    ThrowRejected,
    analyze_throw,
    throw_from_flick,
    throw_from_power,
)
from visa_roulette.visa import needs, reachable, requirement
from visa_roulette.wall import build_wall

MAX_BATCH_SAMPLES = 5000
MAX_STREAM_SAMPLES = 500

router = APIRouter()
MAX_CARDS = 200
_cards: "OrderedDict[str, str]" = OrderedDict()


def _keep_card(text: str) -> str:
    """Hold the trip card on the laptop so the QR only carries a short link a phone camera can read."""
    card_id = secrets.token_urlsafe(6)
    _cards[card_id] = text
    while len(_cards) > MAX_CARDS:
        _cards.popitem(last=False)
    return card_id
Reading = Annotated[list[float], Field(min_length=4, max_length=4)]


class Hub:
    """Fan-out from the ESP32 (or a phone) to every open browser."""

    def __init__(self) -> None:
        self.viewers: set = set()
        self.devices = 0

    async def broadcast(self, message: dict) -> None:
        for viewer in list(self.viewers):
            try:
                await viewer.send_json(message)
            except Exception:  # a dead socket must not stop the others
                self.viewers.discard(viewer)


class MrzIn(BaseModel):
    mrz_lines: list[str] = Field(min_length=2, max_length=2)


class FlickIn(BaseModel):
    dx: float = Field(allow_inf_nan=False, ge=-10_000, le=10_000)
    dy: float = Field(allow_inf_nan=False, ge=-10_000, le=10_000)
    dt_ms: float = Field(allow_inf_nan=False, le=10_000)


class SwitchIn(BaseModel):
    heading_deg: float = Field(allow_inf_nan=False)
    power: float = Field(allow_inf_nan=False)


class TrackPoint(BaseModel):
    t_ms: float = Field(ge=0, le=20_000, allow_inf_nan=False)
    cx: float = Field(ge=0, le=1, allow_inf_nan=False)
    cy: float = Field(ge=0, le=1, allow_inf_nan=False)
    w: float = Field(gt=0, le=1, allow_inf_nan=False)


class CameraIn(BaseModel):
    track: list[TrackPoint] = Field(min_length=1, max_length=120)


class ImuIn(BaseModel):
    samples: list[Reading] = Field(max_length=MAX_BATCH_SAMPLES)


class LandingIn(BaseModel):
    origin: str = Field(pattern=r"^[A-Z]{3}$")
    heading_deg: float = Field(ge=0, lt=360, allow_inf_nan=False)
    distance_km: float = Field(ge=0, le=20_000, allow_inf_nan=False)
    nationality: Iso3 | None = None
    visas: list[VisaHeld] = Field(default_factory=list, max_length=10)


class VisaIn(BaseModel):
    nationality: Iso3
    visas: list[VisaHeld] = Field(default_factory=list, max_length=10)


class VisaRequirementIn(VisaIn):
    destination: Iso3


class Leave(BaseModel):
    """What the traveller chooses to leave in the souvenir swap. Everything is optional and anonymous."""

    nickname: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class HandoffIn(Handoff):
    issued: date = Field(default_factory=date.today)
    leave: Leave | None = None


journal = Journal(JOURNAL_PATH)


@router.get("/api/countries")
async def country_list() -> list:
    return [
        {**dataclasses.asdict(country), **dict(zip(("lat", "lon"), geo.country_centroid(country.iso3)))}
        for country in geo.countries()
    ]


@router.post("/api/profile")
async def profile(body: TravelerProfile) -> dict:
    return body.model_dump(mode="json")


@router.post("/api/profile/prefill")
async def profile_prefill(body: MrzIn) -> dict:
    try:
        td3 = parse_td3(*body.mrz_lines)
    except ValueError as exc:
        raise ScanError("bad_mrz", str(exc)) from None
    return prefill_from_mrz(td3, body.mrz_lines[0], date.today())


@router.post("/api/throw/flick")
async def throw_flick(body: FlickIn) -> dict:
    return dataclasses.asdict(throw_from_flick(body.dx, body.dy, body.dt_ms))


@router.post("/api/throw/camera")
async def throw_camera(body: CameraIn) -> dict:
    return dataclasses.asdict(throw_from_camera([point.model_dump() for point in body.track]))


@router.post("/api/throw/switch")
async def throw_switch(body: SwitchIn) -> dict:
    return dataclasses.asdict(throw_from_power(body.heading_deg, body.power))


@router.post("/api/throw/imu")
async def throw_imu(body: ImuIn) -> dict:
    return dataclasses.asdict(analyze_throw([Sample(*row) for row in body.samples]))


@router.post("/api/landing")
async def landing(body: LandingIn) -> dict:
    try:
        start = geo.country_centroid(body.origin)
    except ValueError:
        raise ScanError("bad_origin", "That starting country is not known.") from None
    only = frozenset(reachable(body.nationality, body.visas)) if body.nationality else None
    result = geo.resolve_landing(body.origin, body.heading_deg, body.distance_km, only or None)
    return {**dataclasses.asdict(result), "start": {"lat": start[0], "lon": start[1]}}


@router.post("/api/visa/requirement")
async def visa_requirement(body: VisaRequirementIn) -> dict:
    if not (geo.is_country(body.nationality) and geo.is_country(body.destination)):
        raise ScanError("bad_country", "That country is not known.", 422)
    verdict = requirement(body.nationality, body.destination, body.visas)
    return {**dataclasses.asdict(verdict), "needs": needs(verdict.status, body.destination)}


class DuelIn(BaseModel):
    destination: Iso3
    a: VisaIn
    b: VisaIn


@router.post("/api/duel")
async def passport_duel(body: DuelIn) -> dict:
    for code in (body.destination, body.a.nationality, body.b.nationality):
        if not geo.is_country(code):
            raise ScanError("bad_country", "That country is not known.", 422)
    return duel(body.a.nationality, body.b.nationality, body.destination, body.a.visas, body.b.visas)


class PickIn(BaseModel):
    choice: Literal["passport", "hotel", "return"]


def _known_destination(iso3: str) -> str:
    if not (re.fullmatch(r"[A-Z]{3}", iso3) and geo.is_country(iso3)):
        raise ScanError("bad_country", "That country is not known.", 422)
    return iso3


@router.get("/api/pick/{iso3}")
async def pick_deal(iso3: str) -> dict:
    return {"destination": _known_destination(iso3), "documents": pick.deal(iso3)}


@router.post("/api/pick/{iso3}/answer")
async def pick_answer(iso3: str, body: PickIn) -> dict:
    return pick.answer(_known_destination(iso3), body.choice)


class AskIn(VisaIn):
    destination: Iso3
    question: str = Field(min_length=1, max_length=500)


@router.post("/api/operator/ask")
async def operator_ask(body: AskIn) -> dict:
    if not (geo.is_country(body.nationality) and geo.is_country(body.destination)):
        raise ScanError("bad_country", "That country is not known.", 422)
    return await run_in_threadpool(booth_operator.ask, body.question, body.nationality, body.destination, body.visas)


class OfficerStartIn(VisaIn):
    destination: Iso3


class OfficerTurnIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    said: str = Field(max_length=2000)


@router.post("/api/officer/start")
async def officer_start(body: OfficerStartIn) -> dict:
    try:
        return await run_in_threadpool(officer_flow.start, body.nationality, body.destination, body.visas)
    except ValueError:
        raise ScanError("bad_country", "That country is not known.", 422)


@router.post("/api/officer/turn")
async def officer_turn(body: OfficerTurnIn) -> dict:
    try:
        return await run_in_threadpool(officer_flow.turn, body.session_id, body.said)
    except KeyError:
        raise HTTPException(status_code=404, detail="That interview is over or unknown.")


@router.post("/api/officer/listen")
async def officer_listen(request: Request, session_id: str | None = None) -> dict:
    data = await request.body()
    if not data:
        raise ScanError("no_audio", "No audio was received.", 422)
    if len(data) > stt.MAX_BYTES:
        raise HTTPException(status_code=413, detail="That recording is too long.")
    try:
        heard = await run_in_threadpool(stt.transcribe, data)
    except stt.SttUnavailable:
        raise ScanError("stt_unavailable", "Speech recognition is not installed on this booth.", 503)
    except (stt.SttError, ValueError):
        raise ScanError("bad_audio", "That audio could not be read.", 422)
    if session_id is None:
        return {"text": heard}
    try:
        return {**await run_in_threadpool(officer_flow.turn, session_id, heard), "heard": heard}
    except KeyError:
        raise HTTPException(status_code=404, detail="That interview is over or unknown.")


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=tts.MAX_TEXT)
    voice: str = Field(default="en-neutral", max_length=20)


@router.post("/api/officer/speak")
async def officer_speak(body: SpeakIn) -> Response:
    spoken = tts.clean(body.text)
    if not spoken:
        raise ScanError("no_text", "Nothing to say.", 422)
    try:
        audio = await run_in_threadpool(tts.synthesize, spoken, body.voice)
    except tts.TtsUnavailable:
        raise ScanError("tts_unavailable", "Speech output is not available on this machine.", 503)
    return Response(content=audio, media_type="audio/wav")


@router.get("/api/destination/{iso3}")
async def destination_get(iso3: str) -> dict:
    info = destination_info.lookup(iso3.upper())
    if info is None:
        raise ScanError("bad_country", "That country is not known.", 422)
    return info


@router.post("/api/visa/map")
async def visa_map(body: VisaIn) -> dict:
    if not geo.is_country(body.nationality):
        raise ScanError("bad_country", "That country is not known.", 422)
    return reachable(body.nationality, body.visas)


def _lan_ip() -> str | None:
    """This laptop's address on the local network. A UDP connect sends no packet, it only picks the route."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def _phone_origin(request: Request) -> str:
    """Origin a phone on the same Wi-Fi can reach: a localhost URL on a QR code would open the phone itself."""
    host = request.url.hostname or ""
    origin = str(request.base_url).rstrip("/")
    if host in ("localhost", "127.0.0.1", "::1") and (ip := _lan_ip()) and not ip.startswith("127."):
        return origin.replace(request.url.netloc, f"{ip}:{request.url.port}" if request.url.port else ip, 1)
    return origin


def _swap_souvenir(body: HandoffIn, status: str) -> Souvenir | None:
    """Leave this traveller's souvenir, take a stranger's, and work out what that stranger's trip would be for you."""
    mine = Souvenir(
        origin=body.profile.origin,
        nationality=body.profile.nationality,
        status=status,
        landing_iso3=body.landing_iso3,
        nickname=clean(body.leave.nickname, MAX_NICKNAME, DEFAULT_NICKNAME),
        note=clean(body.leave.note, MAX_NOTE, DEFAULT_NOTE),
    )
    theirs = journal.swap(mine)
    if theirs is None:
        return None
    verdict = requirement(body.profile.nationality, theirs.landing_iso3, body.profile.visas)
    return theirs.model_copy(update={"nationality": None, "status": None, "for_you_status": verdict.status, "for_you_label": verdict.label[:40]})


@router.get("/api/wall")
async def wall() -> dict:
    return build_wall(journal.all())


@router.get("/api/handoff/{card_id}")
async def handoff_card(card_id: str) -> dict:
    text = _cards.get(card_id)
    if text is None:
        raise HTTPException(status_code=404, detail="That code has expired. Scan the screen again.")
    return {"text": text}


@router.post("/api/handoff")
async def handoff(request: Request, body: HandoffIn) -> dict:
    if not body.consent:
        raise ScanError("no_consent", "Agree to the trip and budget first.")
    verdict = requirement(body.profile.nationality, body.landing_iso3, body.profile.visas)
    stranger = _swap_souvenir(body, verdict.status) if body.leave is not None else None
    card = Handoff.model_validate({
        **body.model_dump(exclude={"leave"}),
        "visa": VisaVerdict(status=verdict.status, label=verdict.label, as_of=verdict.as_of, source_url=verdict.source_url),
        "needs": [item["label"][:48] for item in needs(verdict.status, body.landing_iso3)["items"]][:8],
        "stranger": stranger,
    })
    text = encode_handoff(card)
    card_id = _keep_card(text)
    url = f"{_phone_origin(request)}/phone.html#{card_id}"
    matrix = qr_matrix(url)
    return {"stranger": card.stranger.model_dump(mode="json") if card.stranger else None, "text": text, "url": url, "matrix": matrix, "size": len(matrix)}


def _samples_from(payload) -> list:
    rows = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > MAX_STREAM_SAMPLES:
        raise ValueError("expected {\"samples\": [[t, ax, ay, az], ...]} with at most 500 rows")
    return [Sample(*ImuIn(samples=[row]).samples[0]) for row in rows]


@router.websocket("/ws/imu")
async def imu_device(socket: WebSocket) -> None:
    hub: Hub = socket.app.state.hub
    await socket.accept()
    hub.devices += 1
    await hub.broadcast({"type": "device", "online": True})
    detector = ThrowDetector()
    try:
        while True:
            try:
                samples = _samples_from(json.loads(await socket.receive_text()))
            except ValueError as exc:  # bad JSON or bad rows: report, keep listening
                await hub.broadcast({"type": "device_error", "message": str(exc)[:200]})
                continue
            for sample in samples:
                outcome = detector.feed(sample)
                if isinstance(outcome, ThrowRejected):
                    await hub.broadcast({"type": "rejected", **dataclasses.asdict(outcome)})
                elif outcome is not None:
                    await hub.broadcast({"type": "throw", **dataclasses.asdict(outcome)})
    except WebSocketDisconnect:
        pass
    finally:
        hub.devices -= 1
        await hub.broadcast({"type": "device", "online": hub.devices > 0})


@router.websocket("/ws/throw")
async def throw_viewer(socket: WebSocket) -> None:
    hub: Hub = socket.app.state.hub
    await socket.accept()
    hub.viewers.add(socket)
    try:
        await socket.send_json({"type": "hello", "device_online": hub.devices > 0})
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.viewers.discard(socket)
