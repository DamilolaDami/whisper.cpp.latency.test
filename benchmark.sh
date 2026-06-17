#!/usr/bin/env bash
# Usage:
#   ./benchmark.sh <url> <audio_file> [iterations]
# Example:
#   ./benchmark.sh https://your-app.up.railway.app samples/jfk.wav 10

set -euo pipefail

URL="${1:-http://localhost:8080}"
AUDIO="${2:-samples/jfk.wav}"
ITERS="${3:-5}"

if [[ ! -f "$AUDIO" ]]; then
    echo "Audio file not found: $AUDIO" >&2
    echo "Hint: grab a sample with:" >&2
    echo "  curl -L -o samples/jfk.wav https://github.com/ggerganov/whisper.cpp/raw/master/samples/jfk.wav" >&2
    exit 1
fi

# Audio duration via ffprobe (if available) for real-time-factor calc.
DURATION=""
if command -v ffprobe >/dev/null 2>&1; then
    DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUDIO" 2>/dev/null || true)
fi

echo "Endpoint:  $URL/inference"
echo "Audio:     $AUDIO ${DURATION:+(${DURATION}s)}"
echo "Iters:     $ITERS"
echo

total=0
for i in $(seq 1 "$ITERS"); do
    t=$(curl -s -o /dev/null -w '%{time_total}' \
        -X POST "$URL/inference" \
        -H 'Content-Type: multipart/form-data' \
        -F "file=@${AUDIO}" \
        -F 'response_format=json')
    printf "  run %02d: %ss\n" "$i" "$t"
    total=$(echo "$total + $t" | bc -l)
done

avg=$(echo "scale=3; $total / $ITERS" | bc -l)
echo
echo "Average latency: ${avg}s"

if [[ -n "$DURATION" ]]; then
    rtf=$(echo "scale=3; $avg / $DURATION" | bc -l)
    echo "Real-time factor: ${rtf}x (lower is faster; <1 = faster than real-time)"
fi
