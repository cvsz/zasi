#!/usr/bin/env python3
"""Measure an HTTPS staging endpoint and emit machine-verifiable canary evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects so evidence cannot silently measure another endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _validate_endpoint(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("endpoint must be an HTTPS URL without credentials or fragment")


def _artifact_digest(payload: dict[str, object]) -> str:
    """Return the SHA-256 of the canonical JSON measurement payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def verify_artifact(result: dict[str, object]) -> bool:
    """Verify that a measurement result still matches its canonical payload digest."""
    digest = result.get("artifact_sha256")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return False
    payload = {key: value for key, value in result.items() if key != "artifact_sha256"}
    return digest == _artifact_digest(payload)


def measure(url: str, requests: int, timeout: float) -> dict[str, object]:
    _validate_endpoint(url)
    if requests < 20:
        raise ValueError("requests must be at least 20")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    opener = urllib.request.build_opener(_NoRedirect())
    durations: list[float] = []
    failures = 0
    for _ in range(requests):
        started = time.perf_counter()
        try:
            with opener.open(url, timeout=timeout) as response:  # noqa: S310 -- HTTPS validated above
                # Consume the complete response under the configured socket timeout so
                # p95 represents end-to-end response latency, not time-to-first-byte.
                response.read()
                final_url = response.geturl()
                if final_url != url or not 200 <= response.status < 300:
                    failures += 1
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            failures += 1
        finally:
            durations.append((time.perf_counter() - started) * 1000)

    ordered = sorted(durations)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    result: dict[str, object] = {
        "schema_version": 1,
        "status": "passed" if failures / requests <= 0.01 and ordered[p95_index] <= 2000 else "failed",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "measurement_source": "external-http-probe",
        "endpoint_url": url,
        "request_count": requests,
        "error_count": failures,
        "error_rate": failures / requests,
        "p95_ms": round(ordered[p95_index], 3),
    }
    result["artifact_sha256"] = _artifact_digest(result)
    return result


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
