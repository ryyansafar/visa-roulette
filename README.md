<p align="center">
  <img src="assets/logo.svg" alt="Logo" width="96">
</p>

<h1 align="center">VISA ROULETTE</h1>

<p align="center">
  <b>Spin. Throw. Land.</b><br>Clear the border, earn your throw, land anywhere your passport can take you.<br>
  Built for <a href="https://github.com/jasimcm/layover-2026">LAYOVER 2026</a> at TinkerSpace Calicut, 10–11 Oct 2026.
</p>

> **Status:** work in progress, being built during the hackathon. The features below are built and tested; the "still planned" line is not. See [PLAN.md](PLAN.md) for tiers and progress.

## What it is
A travel booth you can play. You walk up to an immigration desk and show a (sample) passport to the camera; OCR reads it and the booth checks it against deterministic rules. A fast-spinning 3D globe lights up with where that passport can go. You throw a paper plane, by webcam flick or an ESP32 board, and the globe slows and lands on a country. The booth then tells you what that passport needs for that destination: visa status, the documents to prepare, and which of them your pre-flight check already covers. Every verdict cites its source.

**Principle:** AI sees. Rules decide. Every verdict cites its source. Passport data stays on the laptop.

## Features
- Immigration desk: show a passport or boarding pass to the webcam (a prop, a fake on a phone, or a QR); Tesseract OCR reads the MRZ, zxing reads the IATA barcode, both with check-digit validation
- Interactive pre-flight checklist: each item ticks from a cited rule and opens its evidence
- Visa-aware globe: countries coloured by visa-free / on-arrival / e-visa / visa required for the scanned nationality, plus "unlocked by other visas" rules. Demo rules cover Indian (~110 destinations), US, UK and UAE passports; they are unverified and every verdict links its source and date
- Paper-plane throw with real flight physics (`flight.py`: a 5 g point mass with lift, drag, stall and a dihedral-damped banked turn). Throw the plane straight at the webcam, nose first: the booth tracks the blob, reads the approach speed from how fast it grows, aims by sideways drift and sets the launch angle from the climb (`POST /api/throw/camera`). The ESP32 IMU board also shapes the flight: tilt it when held to bank the plane and its in-flight tumbling (flutter) costs range. Flick and single-switch inputs fly the same model. A fast spinning three.js globe slows and lands with a pin
- Booth officer: a local Ollama model (default `gemma3n:e4b`, override with `VISA_ROULETTE_MODEL`) explains the verdict in plain words, bound to the rules facts; ungrounded or slow answers fall back to a template (`POST /api/operator/ask`)
- Immigration interview: `POST /api/officer/start` and `POST /api/officer/turn` run a scripted, strictness-aware interview per destination (personas in `rules/officer_personas.json`). The backend owns the questions and the stamp (always the rules engine's verdict, with source and as-of date); the local model only adds a short grounded reaction. Strictness values are an unverified synthesis, not official data.
- "What you need": for the landing country, the visa status and the documents to prepare, each linked to the matching pre-flight rule and an official-source link
- QR hand-off: the landing spot becomes a QR (laptop LAN address, no internet needed on the phone) that opens a trip card with the visa verdict, its source and date, pre-flight status and the documents to carry
- Passport duel: a second visitor with a different passport lands on the same country; the booth shows both verdicts side by side and crowns the stronger passport (draws are shown as draws)
- Wrong-Document Pick: after landing, three documents for a made-up traveller are shown and one breaks a cited pre-flight rule (short passport validity or a name mismatch); tap it and the booth reveals the rule and its source
- Souvenir swap and Tonight's Landings wall (`/wall.html`): opt-in, anonymous nickname and note, filtered for rude words; the wall shows live landings, the luckiest passport and paper-plane notes. Stored on the laptop only
- Offline-first: the core flow needs no internet; three.js and all assets are vendored

Still planned: destination pros-and-cons reports, accessible input beyond mouse and camera, WebMCP tools. See [PLAN.md](PLAN.md).

## Stack
Python (FastAPI) backend, Tesseract OCR, zxing, OpenCV, a vanilla ES-module front end with a vendored three.js r170 globe, and an optional ESP32 + IMU board. Visa rules live in `rules/visa_rules.json` and `rules/checklist_rules.json`; both are unverified demo rules and the UI says so.

## Running the booth and the phone handoff
```bash
.venv/bin/python -m uvicorn visa_roulette.api:app --app-dir backend --host 0.0.0.0 --port 8766
```
`--host 0.0.0.0` is required: the QR on the laptop opens a short link (`http://<laptop-LAN-ip>:8766/phone.html#<id>`) and the phone fetches the card from the laptop, so the phone must be on the same Wi-Fi. The QR holds only that short link (about 33x33 modules), so any camera app reads it. Cards live in memory (last 200) and expire on restart.

The booth operator is a local Ollama model (`VISA_ROULETTE_MODEL`, default `gemma3n:e4b`). The server warms it at startup so the first answer is not a cold start; replies are trimmed to two plain sentences and fall back to a rules template if the model is slow, down or says anything the rules do not contain.

## Checklist engine
`backend/visa_roulette/checklist.py` turns a passport, boarding pass, bookings and bag into a list of items. Every item carries its rule id, source link, "as of" date and a `verified` flag. All rules in `rules/checklist_rules.json` are currently unverified demo rules drawn from public articles, and the UI must say so.

## Design
Direction and tokens: [docs/DESIGN.md](docs/DESIGN.md), `web/styles/tokens.css`.

## Specimen props (fake passport, boarding pass, bookings)
Three fictional travellers with a SPECIMEN watermark, a made-up airline, and checksum-valid passport MRZs and IATA boarding-pass barcodes. They exist only to demo the booth.

```bash
uv venv .venv-tools && uv pip install --python .venv-tools/bin/python -r tools/requirements.txt
.venv-tools/bin/python tools/make_fixtures.py          # writes fixtures/
python3 -m http.server 8000 --directory fixtures --bind 0.0.0.0
# open http://<laptop-ip>:8000/wallet.html on a phone on the same Wi-Fi
cd backend && ../.venv-tools/bin/python -m pytest -q    # 322 tests
```

| Persona | Trap | Expected |
|---|---|---|
| Lakshmi | passport has under 6 months validity | HELD |
| Arjun | none | CLEARED |
| Shafeeq | hotel booking name differs from passport | HELD |

## Data and credits
- Earth textures: NASA Blue Marble Next Generation (5400x2700 topography and bathymetry) and NASA cloud composite; night lights and bump map from the [globe.gl](https://github.com/vasturiano/globe.gl) examples
- Fonts via [Fontsource](https://fontsource.org): Space Grotesk, IBM Plex Mono, Barrio (open-source fonts; confirm licences before any public release)
- Country polygons: [Natural Earth](https://www.naturalearthdata.com/) (public domain)
- Destination guides: [Wikivoyage](https://en.wikivoyage.org) (CC BY-SA 4.0, attribution required)
- Advisories: UK FCDO and US State Department public feeds
- Visa data: community passport-index dataset plus rules verified against official sources, each with a source link and "as of" date

## Disclaimer
Informational only. Visa and customs rules change. Always verify with the official source before you travel. Use only sample or fake passports with this project.

## Team
- [Ryyan Safar](https://github.com/ryyansafar)
- [Fathima](https://github.com/fathima-004)

## Socials and support
- Portfolio: https://ryyansafar.site
- GitHub: https://github.com/ryyansafar
- Buy Me a Coffee: https://buymeacoffee.com/ryyansafar
- PayPal: https://www.paypal.com/paypalme/ryyansafar
- Razorpay: https://razorpay.me/@ryyansafar
