# VISA ROULETTE — LAYOVER 2026 plan

Build 6 PM–6 AM. Judging 7–9:30 AM: booth round (judges walk the floor), then ~2 min finalist pitch.
Rubric (50): What was built 20 · Creativity 10 · Travel connection 10 · Execution 5 · Demo 5.

**Rule for this plan:** a feature only stays if a judge can SEE it earn a specific mark.
**Pitch:** Check in, pass your pre-flight checklist, earn your throw, land anywhere your passport allows,
and take the result home as a QR. Works with no internet. AI sees, rules decide, every verdict cites its source.

## The judge flow (booth loop, about 90 s) mapped to the rubric
| Beat | What the judge does / sees | Marks it earns |
|---|---|---|
| 1. Check in (10 s) | Scans their own generated boarding pass; real IATA barcode decoded; greeted by name | Built (BCBP decode), Travel (a boarding pass), Demo (their own pass) |
| 2. Pre-flight checklist (25 s) | Puts passport on the pad; MRZ read by OCR and validated; checklist ticks live, each item tappable for its rule + source; a red item shows how to fix it | Built (OCR-tolerant MRZ, cited rules engine), Execution (deterministic, offline), Travel |
| 3. Earn the throw (20 s) | Checklist clear -> stamp -> throw a dart (single key, head tilt, flick) at the spinning globe; budget + continent filters | Creativity, Travel, Demo; accessible input = Creativity + Travel (accessibility lane) |
| 4. Landing report (20 s) | Country report: pros/cons with verbatim quotes + links, advisory level, Outlook score breakdown, LIVE or CACHED badge | Built (local LLM with quote verification), Travel |
| 5. Take it with you (15 s) | The landing spot melts into a QR; phone opens a mock boarding pass for the new route + the checklist + the report | Creativity, Demo, Travel |

**2-minute pitch:** problem (30 s) -> run beats 1-5 live (60 s) -> how it's built: local AI, rules decide, offline (20 s)
-> accessibility + who it helps (10 s). Say the rubric words out loud: built, creative, travel, executed, demoed.

## Interactive checklist (the spine of the booth)
Auto items (ticked by the engine, each with rule id, source_url, as_of, fix hint):
- Passport check digits valid · valid for 6+ months on travel date · name matches boarding pass, return ticket, hotel
- Return ticket present · bag items allowed (3 demo items only)
Manual items (judge taps): travel insurance, prescription copy, travel funds proof.
UI: role="checklist", keyboard toggle, aria-live announcements, evidence drawer per item.
State updates create new objects; keep a copy in localStorage so a refresh doesn't lose it.

## Offline-first design (no internet must never break the demo)
- Tier A, zero internet: beats 1, 2, 3, 5. Boarding pass, MRZ, checklist, rules, globe, throw, QR, phone page.
- Tier B, better with internet: live news refresh, booking links (shown greyed "online only" when offline).
- Vendor everything: three.js, globe.gl, QR lib, MediaPipe wasm + model files. No CDN anywhere.
- Models local: Ollama (gemma3n:e4b present), Tesseract eng present. Whisper weights NOT cached yet.
- Pre-cache reports for ~20 destinations with fetched_at; 2 s network timeout then fall back to cache; badge "CACHED (as of ...)".
- Phone page is static and served from the laptop over a hotspot (needs no internet). QR payload is self-contained.
- WebMCP agent mode needs a cloud agent, so keep manual buttons as the offline path.
- Pitch it: "Built for the layover. No signal at the gate? Still works."

## Triage
KEEP: beats 1-5, accessible throw inputs (switch + mouse first, head tilt if time).
FLOURISH, only after beats 1-5 run end to end twice: WebMCP agent mode (20 s), voice commands.
CUT: skydive sprite, duel mode, VoIP, face match, Malayalam voice, local-LLM officer persona.

## Local AI stack (M2 / 16 GB)
LLM gemma3n:e4b now (qwen3.5:4b if the pull ever finishes). JSON out, every pro/con carries a verbatim quote and
code drops quotes not found in the source. OCR: Tesseract (works) + Apple Vision via ocrmac if installed.
ASR: only if Whisper weights get downloaded. Embeddings: sentence-transformers for mood ranking.

## Data sources (cache before demo)
Visa: passport-index-dataset (archived Jan 2025, patch India) + verified combo rules, each with source_url + as_of.
Articles: Google News RSS (headlines), Wikivoyage API (CC BY-SA, credit), UK FCDO Atom, US State Dept RSS.
Prices: curated estimate bands labelled "estimate, as of date". Affiliate: deep links with AFFILIATE_ID env, labelled.

## Tiers and hours (H0 = 6 PM)
| Tier | Scope | Hours | Status |
|---|---|---|---|
| 1 | Boarding pass + passport engines, props, tests | 3 | DONE (54 tests, props, wallet page) |
| 1b | Booth spine: scan loop + interactive checklist + stamp | 2.5 | todo |
| 2 | Globe + dart + visa/budget filter + switch/mouse input | 3.5 | todo |
| 3 | Destination report (cached first, live refresh) | 2.5 | todo |
| 4 | QR morph + phone page (mock pass, checklist, report) | 1 | todo |
| 5 | Offline hardening + rehearsal | 1.5 | todo |
Feature freeze 4:30 AM. Sleep in staggered 2-3 h shifts.

## Split (adjust freely)
- Ryyan: scan loop, rules engine + checklist logic, report pipeline, caching, offline.
- Fathima: globe visuals + dart animation, checklist UI + accessibility, QR morph, phone page, pitch.

## Offline readiness (audit)
- [x] ollama + gemma3n:e4b, Tesseract eng, MRZ/BCBP engines, fixtures, globe textures + country polygons
- [ ] npm: three, globe.gl, QR lib, MediaPipe wasm/models vendored into the repo
- [ ] Whisper weights + mlx-whisper/ocrmac (install failed on a network timeout; retry with UV_HTTP_TIMEOUT=120)
- [ ] ~20 destination reports cached; 8-10 combo rules verified with sources
- [ ] 90-second booth script + 2-minute pitch rehearsed against the table above

## Risks
Scope (biggest). Wrong visa rule on stage (show as_of + source). Venue Wi-Fi dropping mid-download.
Use fake passports only; informational, "verify before travel".
