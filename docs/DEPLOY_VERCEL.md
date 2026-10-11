# Deploying Visa Roulette to Vercel

A hosted copy is a demo of the screens and the rules engine. The booth keeps the hardware parts.

## What runs where

| Part | Hosted (Vercel) | Booth only |
| --- | --- | --- |
| Pages, globe, fonts, place photos, sample prop images | CDN (static `public/`) | |
| `/api/health`, `/api/profile`, `/api/visa/*`, `/api/checklist`, `/api/demo/personas`, `/api/handoff`, `/api/wall`, `/api/duel`, `/api/pick/*` | Python function `api/index.py` | |
| Scanning the sample travellers' passport and boarding pass | Works: byte-identical sample images are answered from `fixtures/manifest.json` | |
| Scanning any other photo (Tesseract, OpenCV, zxing) | Clean 503 `unavailable_on_hosted` | Works |
| ESP32 board, `/ws/imu`, `/ws/throw`, camera throw | Not routed; the page skips the board socket | Works |
| Speech-to-text, text-to-speech, local LLM operator | Not available; the operator falls back to rules | Works |

Layout: `scripts/vercel_build.sh` copies `web/`, `assets/` and `fixtures/` into `public/` (gitignored). Only the globe files that `web/` names are shipped, so the large textures stay out. `.vercelignore` keeps `.venv`, `data/`, `firmware/` (including every `secrets.h`), `docs/` and tests off the upload.

## Commands (run from the repo root)

```
vercel login
vercel link
vercel deploy --prod
```

`vercel link` asks for a project name; accept the suggested one or pick your own. The framework preset should read "Other".

## Environment variables

None are required. Vercel sets `VERCEL`, which turns hosted mode on. Optional:

- `VISA_ROULETTE_HOSTED=1` forces hosted mode (useful for a local run of the function).
- `VISA_ROULETTE_JOURNAL` overrides where souvenirs are written; on Vercel it defaults to `/tmp/visa_roulette_souvenirs.jsonl`.

## Check the deployment

```
python3 scripts/smoke_hosted.py https://<deployment-url>
```

It checks the static pages and assets, the JSON endpoints, a sample-traveller scan followed by a checklist, and the 503 for unknown images.

To rehearse locally without Vercel:

```
bash scripts/vercel_build.sh
python3 -m http.server 8791 --directory public &
VISA_ROULETTE_HOSTED=1 python3 -m uvicorn --app-dir . api.index:app --port 8790 &
python3 scripts/smoke_hosted.py http://127.0.0.1:8791 http://127.0.0.1:8790
```

Use ports other than 8766 if a booth server is running.

## Known limits of a hosted copy

- Officer interview state and the wall journal live in the memory or `/tmp` of one serverless instance. A cold start or a second instance loses them: the desk shows a retry message, and the wall falls back to its seed entries.
- The phone hand-off carries the whole card in the URL fragment (`/phone.html#VR1...`) instead of a server-side id, so it works across instances.
- Functions are capped at 15 s (`maxDuration` in `vercel.json`).
