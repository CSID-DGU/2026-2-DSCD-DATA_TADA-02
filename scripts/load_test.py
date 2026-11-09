"""Read-only server load probe. Excludes paid LLM calls and produces a JSON artifact."""
import argparse
import asyncio
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import httpx


async def run(args):
    parsed = urlparse(args.base_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("This starter probe is restricted to localhost.")
    semaphore = asyncio.Semaphore(args.concurrency)
    paths = ["/api/v1/areas?q=성수", "/api/v1/areas/3120052/analysis", "/health/ready"]
    durations, statuses, timings = [], Counter(), []
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout) as client:
        # Warm-up is separate and not counted in the measured sample.
        for path in paths:
            response = await client.get(path)
            response.raise_for_status()

        async def request(index):
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(paths[index % len(paths)])
                    statuses[str(response.status_code)] += 1
                    server = response.headers.get("server-timing", "")
                    if server.startswith("app;dur="):
                        timings.append(float(server.removeprefix("app;dur=")))
                except httpx.HTTPError:
                    statuses["transport_error"] += 1
                finally:
                    durations.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        await asyncio.gather(*(request(i) for i in range(args.requests)))
        elapsed = time.perf_counter() - started
    durations.sort()
    percentile = lambda p: durations[min(len(durations) - 1, math.ceil(len(durations) * p) - 1)]
    errors = sum(count for status, count in statuses.items() if not status.startswith("2"))
    result = {
        "target": args.base_url, "scope": "local warm read-only API mix, no external LLM",
        "requests": args.requests, "concurrency": args.concurrency, "elapsed_seconds": elapsed,
        "requests_per_second": args.requests / elapsed, "statuses": dict(statuses),
        "error_rate": errors / args.requests, "client_latency_ms": {"p50": percentile(.5), "p95": percentile(.95), "p99": percentile(.99), "max": durations[-1]},
        "server_header_ms_mean": statistics.mean(timings) if timings else None,
        "limits": "Local synthetic-data probe only; not Cloud Run capacity, cold start, availability or production SLO evidence.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--output", default="tmp/load-test.json")
    args = parser.parse_args()
    if not 1 <= args.requests <= 10000 or not 1 <= args.concurrency <= 100:
        parser.error("requests must be 1..10000, concurrency 1..100")
    raise SystemExit(asyncio.run(run(args)))
