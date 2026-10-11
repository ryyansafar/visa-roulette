#!/usr/bin/env bash
# Assemble public/ for Vercel: web/ at the root, plus the assets/ and fixtures/ folders that live outside it, so the
# absolute URLs the pages use (/assets/..., /fixtures/..., /vendor/..., /js/..., /styles/...) resolve on the CDN.
# Runs on Vercel as the build command and locally (`bash scripts/vercel_build.sh`). Plain POSIX tools only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/public}"

rm -rf "$OUT"
mkdir -p "$OUT/assets"

cp -R "$ROOT/web/." "$OUT/"
find "$OUT" -name '*.test.mjs' -delete

cp -R "$ROOT/assets/." "$OUT/assets/"
mkdir -p "$OUT/fixtures"
cp -R "$ROOT/fixtures/." "$OUT/fixtures/"  # merges with anything web/ already ships under fixtures/

# assets/globe holds ~8 MB of textures. Ship only the files the pages actually reference by name, so dropping a texture
# from web/ drops it from the deploy automatically.
rm -rf "$OUT/assets/globe"
mkdir -p "$OUT/assets/globe"
{ grep -rhoE '/assets/globe/[A-Za-z0-9._-]+' "$ROOT/web" --include='*.js' --include='*.html' --include='*.css' || true; } \
  | sort -u | while read -r ref; do
    if [ -f "$ROOT$ref" ]; then
      cp "$ROOT$ref" "$OUT$ref"
    else
      echo "vercel_build: warning: $ref is referenced in web/ but missing from assets/" >&2
    fi
  done

echo "vercel_build: $(find "$OUT" -type f | wc -l | tr -d ' ') files, $(du -sh "$OUT" | cut -f1) in ${OUT#$ROOT/}"
