#!/bin/sh
# Copies the specimen passports, boarding passes and papers to a USB-connected Android phone's gallery.
# iPhone: no adb; AirDrop the phone_props/ folder or drag it into Finder > iPhone > Files.
set -e
cd "$(dirname "$0")/.."
DEST=/sdcard/Pictures/VisaRoulette
[ -d phone_props ] || { echo "phone_props/ missing"; exit 1; }
adb get-state >/dev/null 2>&1 || { echo "No Android phone found. Plug it in, enable USB debugging, accept the prompt."; exit 1; }
adb shell mkdir -p "$DEST"
for f in phone_props/*.png; do
  adb push "$f" "$DEST/" >/dev/null
  adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://$DEST/$(basename "$f")" >/dev/null
done
echo "Sent $(ls phone_props/*.png | wc -l | tr -d ' ') files to $DEST"
