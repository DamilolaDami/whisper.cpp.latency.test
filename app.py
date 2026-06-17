import json
import logging
import os
import sys
import time
import uuid

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

WHISPER_URL = os.environ.get("WHISPER_INTERNAL_URL", "http://127.0.0.1:8081")
API_KEY = os.environ.get("API_KEY")  # if unset, auth is disabled
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "300"))

logger = logging.getLogger("whisper-proxy")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_handler)
logger.propagate = False

app = FastAPI(title="whisper.cpp proxy")
_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)


def _log(event: str, **fields):
    logger.info(json.dumps({"event": event, "ts": time.time(), **fields}))


def _check_auth(authorization: str | None):
    if API_KEY is None:
        return
    expected = f"Bearer {API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing api key")


@app.get("/health")
async def health():
    try:
        # whisper-server has no health endpoint; a HEAD to / returns *something*
        # (usually 404) which is enough to confirm the process is up.
        r = await _client.request("HEAD", f"{WHISPER_URL}/", timeout=2.0)
        return {"status": "ok", "upstream_status": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"upstream unreachable: {e}")


@app.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
    language: str | None = Form(None),
    authorization: str | None = Header(default=None),
):
    _check_auth(authorization)

    request_id = str(uuid.uuid4())
    audio_bytes = await file.read()

    _log(
        "request_start",
        request_id=request_id,
        filename=file.filename,
        audio_bytes=len(audio_bytes),
        client=request.client.host if request.client else None,
    )

    started = time.perf_counter()
    try:
        files = {"file": (file.filename or "audio", audio_bytes, file.content_type or "application/octet-stream")}
        data = {"response_format": response_format, "temperature": str(temperature)}
        if language:
            data["language"] = language

        upstream = await _client.post(f"{WHISPER_URL}/inference", files=files, data=data)
        latency_ms = (time.perf_counter() - started) * 1000

        _log(
            "request_done",
            request_id=request_id,
            status=upstream.status_code,
            latency_ms=round(latency_ms, 2),
            audio_bytes=len(audio_bytes),
        )

        content_type = upstream.headers.get("content-type", "application/json")
        return JSONResponse(
            content=upstream.json() if "json" in content_type else {"text": upstream.text},
            status_code=upstream.status_code,
            headers={"X-Request-ID": request_id, "X-Latency-Ms": f"{latency_ms:.1f}"},
        )
    except httpx.RequestError as e:
        latency_ms = (time.perf_counter() - started) * 1000
        _log("request_error", request_id=request_id, error=str(e), latency_ms=round(latency_ms, 2))
        raise HTTPException(status_code=502, detail=f"upstream error: {e}")
