# VISA VERSA — LAYOVER 2026 plan

Build 6 PM–6 AM. Judging 7–9:30 AM (booth round, then ~2 min finalist pitch).
Rubric (50): What was built 20 · Creativity 10 · Travel connection 10 · Execution 5 · Demo 5.

**Pitch:** Clear the border, earn your throw, land anywhere your passport can take you, and the booth
reads the world's news about it. Playable by anyone, including people who can't throw.
AI sees. Rules decide. Every verdict cites its source. Passport data never leaves the laptop.

## Flow (90 s)
1. Judge gets a generated boarding pass (CCJ->DXB, their name, IATA-format barcode). Scan it -> greeted by name.
2. Passport scan (fake/sample): MRZ check digits, validity, nationality -> globe lights up (green/amber/red, blue = unlocked by other visas).
3. Optional bag check (3 trap items) -> CLEARED/HELD stamp with cited rule.
4. Throw: dart, skydive sprite, or accessible input. Lands on a country; filtered by visa + budget; continent selectable.
5. Destination report: verified pros/cons from news + Wikivoyage + advisories, Outlook score with breakdown, "confirm" -> booking links.
6. Passport stamp added; stamped boarding pass out.

## Accessibility (core, not a bolt-on)
All inputs emit the same event `{yaw, pitch, power}` behind one `ThrowInput` interface.
- Single switch (Space/big button): aim sweeps automatically, press to throw (switch scanning).
- Head tilt: MediaPipe face landmarks via webcam, with dead zone + smoothing.
- Voice: "throw", "left", "warmer" via mlx-whisper and/or WebMCP agent.
- IMU dart (ESP32) with tremor low-pass filter. Mouse flick as baseline.
- App: keyboard operable, large targets, aria-live results, captions, honour prefers-reduced-motion (no shake).
Claim "designed with switch-access principles", NOT clinically validated. Ask a mentor/participant to try it.

## Local AI stack (M2 / 16 GB)
- LLM: qwen3.5:4b via Ollama (fallback gemma3n:e4b, already installed). JSON output, each pro/con carries a verbatim quote; code drops any quote not found in the source.
- ASR: mlx-whisper large-v3-turbo (fallback faster-whisper). Malayalam untested; English is the reliable path.
- OCR: Apple Vision via ocrmac, Tesseract fallback.
- Embeddings: sentence-transformers for mood ranking.
- Hand/face: MediaPipe in browser. Do not run two LLMs at once.

## Data sources (cache before demo)
- Visa: passport-index-dataset (archived Jan 2025, stale; patch India row) + verified combo rules (US/UK/Schengen visa unlocks). Each rule: id, source_url, as_of. Verify against official sites.
- Articles: Google News RSS (headlines, redirect links), Wikivoyage API (CC BY-SA, credit it), UK FCDO Atom, US State Dept RSS.
- Geometry: assets/globe (NASA-derived textures, Natural Earth countries with ISO + CONTINENT).
- Affiliate: deep-link templates with AFFILIATE_ID env var, labelled "affiliate link"; IDs pending.
- Prices: curated estimate bands labelled "estimate, as of date". No live fares.

## WebMCP tools (register via @mcp-b polyfill; feature-detect navigator/document.modelContext)
set_budget, select_continent, list_allowed_destinations, throw_dart, get_destination_report,
open_booking_link (requires on-screen confirmation). Never expose passport data; return nationality code + visa status only.
Rules decide; the agent cannot override verdicts. Keep manual buttons as fallback.

## Tiers and hours (H0 = 6 PM)
| Tier | Scope | Hours |
|---|---|---|
| 1 | Boarding pass + passport MRZ + rules + stamp | 3 |
| 2 | Globe + dart + visa/budget filter + switch/mouse input | 3.5 |
| 3 | Destination report (RSS + Wikivoyage + LLM + score + links) | 2.5 |
| 3.5 | WebMCP tools + voice | 1 |
| 4 | Bag check (3 trap items), head-tilt input | 1.5 |
| 5 | Skydive sprite, duel mode, VoIP boarding call, Malayalam voice | only if ahead |
Feature freeze 4:30 AM. Then rehearse. Sleep in staggered 2-3 h shifts.

## Split (adjust freely)
- Ryyan: pipeline (MRZ, rules engine, LLM report), WebMCP, inputs, caching.
- Fathima: globe visuals + dart animation, UI/accessibility, verified visa/destination data, photos, pitch.

## Fallbacks
Simulated booth (BOOTH=sim), mouse throw, cached reports for ~20 demo destinations, cached feeds, manual buttons if WebMCP flag fails.

## Risks
Scope (biggest). Wrong visa rule on stage (show as_of + source). Venue Wi-Fi. Phones need HTTPS for sensors/mic.
Use fake passports only; informational, "verify before travel".

## Before building
- [ ] qwen3.5:4b pulled; mlx-whisper + ocrmac import OK (project .venv)
- [ ] Chrome WebMCP check in console: 'modelContext' in navigator, and in document
- [ ] Cache ~20 destination reports; verify 8-10 combo rules from official sites
- [ ] 90-second script written and timed
