#!/bin/bash
# Capture one PNG per slide using Chrome headless. No npm dependencies.
# Usage: bash tools/screenshot_slides.sh <short|full>
set -e
cd "$(dirname "$0")/.."

VERSION="${1:-short}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

case "$VERSION" in
  short)
    HTML_FILE="docs/slides-short.html"
    SLIDE_COUNT=5
    OUT="docs/assets/slides_png/short"
    ;;
  full)
    HTML_FILE="docs/slides.html"
    SLIDE_COUNT=10
    OUT="docs/assets/slides_png/full"
    ;;
  *)
    echo "Usage: $0 <short|full>"
    exit 1
    ;;
esac

HTML="file://$(pwd)/${HTML_FILE}?mode=video"
mkdir -p "$OUT"

echo "Screenshotting $HTML_FILE ($SLIDE_COUNT slides) → $OUT"

for i in $(seq 1 $SLIDE_COUNT); do
  "$CHROME" \
    --headless=new \
    --disable-gpu \
    --window-size=1920,1080 \
    --force-device-scale-factor=1 \
    --hide-scrollbars \
    --no-sandbox \
    --virtual-time-budget=1500 \
    --screenshot="$(pwd)/$OUT/slide$(printf '%02d' $i).png" \
    "${HTML}#${i}" 2>/dev/null
  echo "  slide$(printf '%02d' $i).png"
done

echo "Done."
