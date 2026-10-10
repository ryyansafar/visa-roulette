"""Routes for the traveller profile, the throw, the landing and the QR hand-off."""

import dataclasses
import json
import socket
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from visa_roulette import geo
from visa_roulette.errors import ScanError
from visa_roulette.souvenirs import JOURNAL_PATH, Journal, Souvenir, clean, DEFAULT_NICKNAME, DEFAULT_NOTE, MAX_NICKNAME, MAX_NOTE
from visa_roulette.handoff import Handoff, VisaVerdict, encode_handoff, qr_matrix
from visa_roulette.mrz import parse_td3
from visa_roulette.profile import Iso3, TravelerProfile, VisaHeld, prefill_from_mrz
from visa_roulette.visa import needs, reachable, requirement
from visa_roulette.wall import build_wall
from visa_roulette.throw import (
    Sample,
    ThrowDetector,
    ThrowRejected,
    analyze_throw,
    throw_from_flick,
    throw_from_power,
)

MAX_BATCH_SAMPLES = 5000
MAX_STREAM_SAMPLES = 500

router = APIRouter()
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


class ImuIn(BaseModel):
    samples: list[Reading] = Field(max_length=MAX_BATCH_SAMPLES)


class LandingIn(BaseModel):
    origin: str = Field(pattern=r"^[A-Z]{3}$")
    heading_deg: float = Field(ge=0, lt=360, allow_inf_nan=False)
    distance_km: float = Field(ge=0, le=20_000, allow_inf_nan=False)
    nationality: Optional[Iso3] = None
    visas: list[VisaHeld] = Field(default_factory=list, max_length=10)


class VisaIn(BaseModel):
    nationality: Iso3
    visas: list[VisaHeld] = Field(default_factory=list, max_length=10)


class VisaRequirementIn(VisaIn):
    destination: Iso3


class Leave(BaseModel):
    """What the traveller chooses to leave in the souvenir swap. Everything is optional and anonymous."""

    nickname: Optional[str] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=500)


class HandoffIn(Handoff):
    issued: date = Field(default_factory=date.today)
    leave: Optional[Leave] = None


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


@router.post("/api/visa/map")
async def visa_map(body: VisaIn) -> dict:
    if not geo.is_country(body.nationality):
        raise ScanError("bad_country", "That country is not known.", 422)
    return reachable(body.nationality, body.visas)


def _lan_ip() -> Optional[str]:
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


def _swap_souvenir(body: HandoffIn, status: str) -> Optional[Souvenir]:
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
    matrix = qr_matrix(text)
    return {"stranger": card.stranger.model_dump(mode="json") if card.stranger else None, "text": text, "url": f"{_phone_origin(request)}/phone.html#{text}", "matrix": matrix, "size": len(matrix)}


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
