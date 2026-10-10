<p align="center">
  <img src="assets/logo.svg" alt="Logo" width="96">
</p>

<h1 align="center">THUNA</h1>

<p align="center">
  Clear the border, earn your throw, land anywhere your passport can take you.<br>
  Built for <a href="https://github.com/jasimcm/layover-2026">LAYOVER 2026</a> at TinkerSpace Calicut, 10–11 Oct 2026.
</p>

> **Status:** work in progress, being built during the hackathon. The feature list below is the plan, not a claim that everything is finished. See [PLAN.md](PLAN.md) for tiers and progress.

## What it is
A travel booth you can play. You scan a (sample) passport, the booth checks it with deterministic rules, and a globe lights up with where that passport can go. You throw a dart at the globe, it lands on a country, and the booth reads recent news and travel guides about that place and gives you an honest pros-and-cons report. Every verdict cites its source.

**Principle:** AI sees. Rules decide. Every verdict cites its source. Passport data stays on the laptop.

## Planned features
- Boarding-pass barcode (IATA format) and passport MRZ parsing with check-digit validation
- Visa-free / on-arrival globe for the scanned nationality, plus "unlocked by other visas" rules
- Dart-throw globe game with budget and continent filters
- Destination report: verified pros and cons, advisory level and an explainable Outlook score
- Accessible input: single switch, head tilt, voice, IMU dart with tremor filtering, mouse
- WebMCP tools so a browser agent can drive the booth
- Local AI only (Ollama, MLX Whisper, Apple Vision OCR, sentence-transformers)

## Stack
Python (FastAPI) backend, three.js globe frontend, Ollama LLM, mlx-whisper, ocrmac, sentence-transformers, MediaPipe, optional ESP32 + IMU.

## Data and credits
- Earth textures: NASA Blue Marble (via the [globe.gl](https://github.com/vasturiano/globe.gl) examples)
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
