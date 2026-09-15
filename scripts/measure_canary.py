#!/usr/bin/env python3
"""Measure an HTTPS staging endpoint and emit machine-verifiable canary evidence."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse


def measure(url: str, requests: int, timeout: float) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("endpoint must be an HTTPS URL without credentials or fragment")
    if requests < 20:
        raise ValueError("requests must be at least 20")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    durations: list[float] = []
    failures = 0
    for _ in range(requests):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 -- HTTPS validated above
                response.read(1)
                if not 200 <= response.status < 400:
                    failures += 1
        except (urllib.error.URLError, TimeoutError, OSError):
            failures += 1
        finally:
            durations.append((time.perf_counter() - started) * 1000)

    ordered = sorted(durations)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return {
        "status": "passed" if failures / requests <= 0.01 and ordered[p95_index] <= 2000 else "failed",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "measurement_source": "external-http-probe",
        "endpoint_url": url,
        "request_count": requests,
        "error_count": failures,
        "error_rate": failures / requests,
        "p95_ms": round(ordered[p95_index], 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        result = measure(args.endpoint, args.requests, args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
