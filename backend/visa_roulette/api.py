"""Booth scan API. Offline-first: nothing here needs the internet."""

import asyncio
import dataclasses
import json
import shutil
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints, field_validator

from visa_roulette import operator as booth_operator
from visa_roulette.bcbp import parse_bcbp
from visa_roulette.checklist import build_checklist
from visa_roulette.errors import ScanError
from visa_roulette.flow_api import Hub
from visa_roulette.flow_api import router as flow_router
from visa_roulette.imaging import load_image
from visa_roulette.mrz import parse_td3
from visa_roulette.mrz_locate import opencv_available
from visa_roulette.scan_boarding import scan_boarding_pass
from visa_roulette.scan_passport import read_mrz
from visa_roulette.throw import ThrowError

ROOT = Path(__file__).resolve().parents[2]
MAX_BODY = 10 * 1024 * 1024
DEMO_IMAGES = ("role_card", "boarding_pass", "passport", "return_ticket", "hotel_booking")

ShortText = Annotated[str, StringConstraints(max_length=80)]
RuleId = Annotated[str, StringConstraints(pattern=r"^R-[A-Z0-9-]{2,24}$")]


class ChecklistRequest(BaseModel):
    mrz_lines: list[str] = Field(min_length=2, max_length=2)
    boarding_pass: str = Field(min_length=60, max_length=200)
    return_ticket_name: ShortText | None = None
    hotel_name: ShortText | None = None
    bag: list[ShortText] = Field(default_factory=list, max_length=50)
    travel_date: date
    ticked: list[RuleId] = Field(default_factory=list, max_length=20)

    @field_validator("mrz_lines")
    @classmethod
    def lines_are_44_chars(cls, lines: list[str]) -> list[str]:
        if any(len(line) != 44 for line in lines):
            raise ValueError("each MRZ line must be exactly 44 characters")
        return lines


async def read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        raise ScanError("too_large", "That upload is too large (10 MB max).", 413)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            raise ScanError("too_large", "That upload is too large (10 MB max).", 413)
        chunks.append(chunk)
    return b"".join(chunks)


def _mrz_payload(scan) -> dict:
    td3 = scan.td3
    fields = {k: v for k, v in dataclasses.asdict(td3).items() if k != "checks"}
    return {
        "lines": [scan.line1, scan.line2],
        "fields": fields,
        "checks": td3.checks,
        "all_checks_pass": td3.all_checks_pass,
    }


def _mount(app: FastAPI, url: str, directory: Path, **kwargs) -> None:
    if directory.is_dir():
        app.mount(url, StaticFiles(directory=directory, **kwargs), name=url.strip("/") or "web")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        warming = asyncio.create_task(asyncio.to_thread(booth_operator.warm))
        yield
        warming.cancel()

    app = FastAPI(title="Visa Roulette booth API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ScanError)
    async def scan_error_handler(_: Request, exc: ScanError) -> JSONResponse:
        return JSONResponse({"detail": {"code": exc.code, "message": exc.message}}, status_code=exc.status)

    @app.exception_handler(ThrowError)
    async def throw_error_handler(_: Request, exc: ThrowError) -> JSONResponse:
        return JSONResponse({"detail": {"code": exc.code, "message": exc.message}}, status_code=422)

    app.state.hub = Hub()
    app.include_router(flow_router)

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "version": app.version,
            "capabilities": {
                "tesseract": shutil.which("tesseract") is not None,
                "opencv": opencv_available(),
                "zxing": True,
            },
        }

    @app.post("/api/scan/boarding-pass")
    async def scan_boarding(request: Request, year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100)):
        image = await run_in_threadpool(load_image, await read_body(request))
        scan = await run_in_threadpool(scan_boarding_pass, image, year)
        return {"raw": scan.raw, "format": scan.format, "boarding_pass": dataclasses.asdict(scan.boarding_pass)}

    @app.post("/api/scan/passport")
    async def scan_passport(request: Request):
        image = await run_in_threadpool(load_image, await read_body(request))
        scan = await run_in_threadpool(read_mrz, image)
        return {"mrz": _mrz_payload(scan), "confidence": scan.score / len(scan.td3.checks), "method": scan.method}

    @app.post("/api/checklist")
    async def checklist(req: ChecklistRequest):
        try:
            mrz = parse_td3(*req.mrz_lines)
        except ValueError as exc:
            raise ScanError("bad_mrz", str(exc)) from None
        try:
            boarding = parse_bcbp(req.boarding_pass, req.travel_date.year)
        except ValueError as exc:
            raise ScanError("bad_boarding_pass", str(exc)) from None
        result = build_checklist(
            mrz=mrz,
            boarding=boarding,
            return_ticket_name=req.return_ticket_name,
            hotel_name=req.hotel_name,
            bag=req.bag,
            travel_date=req.travel_date,
            ticked=frozenset(req.ticked),
        )
        return {
            "verdict": result.verdict,
            "readiness": result.readiness,
            "items": [dataclasses.asdict(item) for item in result.items],
        }

    @app.get("/api/demo/personas")
    async def demo_personas() -> list:
        manifest = json.loads((ROOT / "fixtures" / "manifest.json").read_text())
        return [
            {
                "key": p["key"],
                "expected": p["expected"],
                "expected_reason": p["expected_reason"],
                "booking_name": p["booking_name"],
                "bag": p["bag"],
                "images": {name: f"/fixtures/{p['key']}/{name}.png" for name in DEMO_IMAGES},
            }
            for p in manifest
        ]

    _mount(app, "/fixtures", ROOT / "fixtures")
    _mount(app, "/assets", ROOT / "assets")
    _mount(app, "/", ROOT / "web", html=True)
    return app


app = create_app()
