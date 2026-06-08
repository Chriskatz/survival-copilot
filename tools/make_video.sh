#!/bin/bash
# Build a narrated MP4 from slide PNGs + audio WAVs.
# Usage: bash tools/make_video.sh <short|full>
set -e
cd "$(dirname "$0")/.."

VERSION="${1:-short}"

case "$VERSION" in
  short)
    SLIDES="docs/assets/slides_png/short"
    AUDIO="docs/assets/audio"
    AUDIO_PREFIX="short-s"
    SLIDE_COUNT=5
    OUT="docs/survival-copilot-pitch-short.mp4"
    ;;
  full)
    SLIDES="docs/assets/slides_png/full"
    AUDIO="docs/assets/audio"
    AUDIO_PREFIX="s"
    SLIDE_COUNT=10
    OUT="docs/survival-copilot-pitch-full.mp4"
    ;;
  *)
    echo "Usage: $0 <short|full>"
    exit 1
    ;;
esac

FPS=30
GAP=0.55   # silence gap between narrations
FADE=0.25  # fade-in / fade-out duration

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

echo "Building $VERSION version → $OUT"
echo "Building per-slide clips..."

for i in $(seq 1 $SLIDE_COUNT); do
  WAV="$AUDIO/${AUDIO_PREFIX}${i}.wav"
  PNG="$SLIDES/slide$(printf '%02d' $i).png"
  DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$WAV")
  TOTAL=$(echo "$DUR + $GAP" | bc -l)
  FADE_OUT_ST=$(echo "$DUR - $FADE" | bc -l)

  if [ "$i" -eq "$SLIDE_COUNT" ]; then
    TOTAL=$(echo "$DUR + 0.3" | bc -l)
  fi

  ffmpeg -y \
    -framerate $FPS -loop 1 -t "$TOTAL" -i "$PNG" \
    -i "$WAV" \
    -filter_complex "
      [0:v]fade=t=in:st=0:d=$FADE,fade=t=out:st=$FADE_OUT_ST:d=$FADE[v];
      [1:a]apad=pad_dur=$GAP[a]
    " \
    -map "[v]" -map "[a]" \
    -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p \
    -c:a aac -b:a 192k \
    -t "$TOTAL" \
    "$TMP/clip${i}.mp4" 2>/dev/null
  echo "  clip${i}: ${DUR}s narration + gap = ${TOTAL}s"
done

echo "Concatenating $SLIDE_COUNT clips..."

# Build concat filter dynamically
INPUTS=""
FILTER=""
for i in $(seq 1 $SLIDE_COUNT); do
  INPUTS="$INPUTS -i $TMP/clip${i}.mp4"
  FILTER="${FILTER}[$(( i - 1 )):v][$(( i - 1 )):a]"
done
FILTER="${FILTER}concat=n=${SLIDE_COUNT}:v=1:a=1[vout][aout]"

ffmpeg -y $INPUTS \
  -filter_complex "$FILTER" \
  -map "[vout]" -map "[aout]" \
  -r $FPS \
  -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  "$OUT" 2>&1 | grep -E "^frame=|error|Error"

echo ""
echo "Done: $OUT"
DUR=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$OUT")
echo "Total duration: ${DUR}s"
