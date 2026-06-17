"""
Concurrent load test for the whisper proxy.

Usage:
    python loadtest.py <url> <audio_file> [--concurrency N] [--requests N] [--api-key KEY]

Example:
    python loadtest.py https://your-app.up.railway.app samples/jfk.wav --concurrency 4 --requests 40
"""

import argparse
import asyncio
import statistics
import time
from pathlib import Path

import httpx


async def one_request(client: httpx.AsyncClient, url: str, audio: bytes, filename: str, api_key: str | None):
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    files = {"file": (filename, audio, "audio/wav")}
    data = {"response_format": "json"}

    started = time.perf_counter()
    try:
        r = await client.post(f"{url}/transcribe", files=files, data=data, headers=headers)
        elapsed = time.perf_counter() - started
        return {"ok": r.status_code == 200, "status": r.status_code, "latency": elapsed, "err": None}
    except Exception as e:
        return {"ok": False, "status": None, "latency": time.perf_counter() - started, "err": str(e)}


async def worker(name: int, queue: asyncio.Queue, client, url, audio, filename, api_key, results):
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        res = await one_request(client, url, audio, filename, api_key)
        results.append(res)
        status = res["status"] or "ERR"
        print(f"  [w{name}] status={status} latency={res['latency']:.2f}s")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("audio")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--requests", type=int, default=20)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    audio_path = Path(args.audio)
    audio = audio_path.read_bytes()
    print(f"Endpoint:    {args.url}/transcribe")
    print(f"Audio:       {audio_path} ({len(audio)/1024:.1f} KiB)")
    print(f"Concurrency: {args.concurrency}")
    print(f"Total reqs:  {args.requests}")
    print()

    queue: asyncio.Queue = asyncio.Queue()
    for i in range(args.requests):
        queue.put_nowait(i)

    results: list[dict] = []
    wall_start = time.perf_counter()

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        workers = [
            asyncio.create_task(worker(i, queue, client, args.url, audio, audio_path.name, args.api_key, results))
            for i in range(args.concurrency)
        ]
        await asyncio.gather(*workers)

    wall_elapsed = time.perf_counter() - wall_start

    latencies = [r["latency"] for r in results if r["ok"]]
    errors = [r for r in results if not r["ok"]]

    print()
    print("=" * 50)
    print(f"Wall time:    {wall_elapsed:.2f}s")
    print(f"Successful:   {len(latencies)}/{len(results)}")
    print(f"Errors:       {len(errors)}")
    if latencies:
        latencies.sort()
        print(f"Throughput:   {len(latencies)/wall_elapsed:.2f} req/s")
        print(f"Latency mean: {statistics.mean(latencies):.2f}s")
        print(f"Latency p50:  {latencies[len(latencies)//2]:.2f}s")
        print(f"Latency p95:  {latencies[min(len(latencies)-1, int(len(latencies)*0.95))]:.2f}s")
        print(f"Latency p99:  {latencies[min(len(latencies)-1, int(len(latencies)*0.99))]:.2f}s")
        print(f"Latency max:  {max(latencies):.2f}s")
    if errors:
        print()
        print("Sample errors:")
        for e in errors[:5]:
            print(f"  status={e['status']} err={e['err']}")


if __name__ == "__main__":
    asyncio.run(main())
