#!/usr/bin/env bash
# Starts whisper-server on an internal port, then runs the Python proxy on $PORT.
# If either process dies, the container exits so Railway will restart it.

set -euo pipefail

INTERNAL_PORT="${INTERNAL_PORT:-8081}"
PORT="${PORT:-8080}"
THREADS="${THREADS:-4}"
MODEL="${MODEL:-small.en}"

/app/whisper-server \
    --host 127.0.0.1 \
    --port "${INTERNAL_PORT}" \
    --threads "${THREADS}" \
    --model "/app/models/ggml-${MODEL}.bin" &
WHISPER_PID=$!

export WHISPER_INTERNAL_URL="http://127.0.0.1:${INTERNAL_PORT}"

uvicorn app:app --host 0.0.0.0 --port "${PORT}" --log-level info &
PROXY_PID=$!

# Exit as soon as either process exits, propagating its status.
wait -n "${WHISPER_PID}" "${PROXY_PID}"
EXIT_CODE=$?

kill "${WHISPER_PID}" "${PROXY_PID}" 2>/dev/null || true
exit "${EXIT_CODE}"
