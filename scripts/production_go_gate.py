#!/usr/bin/env python3
"""Validate the external evidence required before a ZASI production release.

This gate intentionally distinguishes CI rehearsal evidence from real staging evidence.
A release candidate is GO only when repository governance is enabled and an external
staging record proves health, World Room smoke, canary SLOs, and immutable rollback.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$")
PASS = "passed"


class GateError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def _passed(obj: Any, name: str) -> dict[str, Any]:
    _require(isinstance(obj, dict), f"{name} must be an object")
    _require(obj.get("status") == PASS, f"{name}.status must be 'passed'")
    return obj


def _https(value: Any, name: str) -> str:
    _require(isinstance(value, str) and value, f"{name} is required")
    parsed = urlparse(value)
    _require(parsed.scheme == "https" and bool(parsed.netloc), f"{name} must be an https URL")
    return value


def _timestamp(value: Any) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), "observed_at must be an RFC3339 UTC timestamp ending in Z")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateError("observed_at is not a valid timestamp") from exc
    _require(result.tzinfo is not None, "observed_at must include timezone information")
    return result.astimezone(timezone.utc)


def validate_evidence(data: dict[str, Any], *, expected_commit: str, main_protected: bool) -> dict[str, Any]:
    _require(main_protected, "main branch is not protected; production GO is forbidden")
    _require(data.get("schema_version") == 1, "schema_version must be 1")

    candidate_commit = data.get("candidate_commit")
    _require(isinstance(candidate_commit, str) and SHA40.fullmatch(candidate_commit) is not None, "candidate_commit must be a lowercase 40-character git SHA")
    _require(SHA40.fullmatch(expected_commit) is not None, "expected commit must be a lowercase 40-character git SHA")
    _require(candidate_commit == expected_commit, "evidence candidate_commit does not match the release commit")

    candidate_image = data.get("candidate_image")
    previous_image = data.get("previous_image")
    _require(isinstance(candidate_image, str) and DIGEST.fullmatch(candidate_image) is not None, "candidate_image must be an immutable GHCR sha256 digest reference")
    _require(isinstance(previous_image, str) and DIGEST.fullmatch(previous_image) is not None, "previous_image must be an immutable GHCR sha256 digest reference")
    _require(candidate_image != previous_image, "candidate_image and previous_image must differ")

    _https(data.get("staging_url"), "staging_url")
    observed_at = _timestamp(data.get("observed_at"))
    _require(observed_at <= datetime.now(timezone.utc), "observed_at cannot be in the future")

    health = _passed(data.get("health"), "health")
    _https(health.get("ready_url"), "health.ready_url")

    world_room = _passed(data.get("world_room"), "world_room")
    _require(isinstance(world_room.get("smoke_case"), str) and world_room["smoke_case"].strip(), "world_room.smoke_case is required")

    canary = _passed(data.get("canary"), "canary")
    request_count = canary.get("request_count")
    error_rate = canary.get("error_rate")
    p95_ms = canary.get("p95_ms")
    _require(isinstance(request_count, int) and not isinstance(request_count, bool) and request_count >= 20, "canary.request_count must be at least 20")
    _require(isinstance(error_rate, (int, float)) and not isinstance(error_rate, bool) and 0 <= float(error_rate) <= 0.01, "canary.error_rate must be between 0 and 0.01")
    _require(isinstance(p95_ms, (int, float)) and not isinstance(p95_ms, bool) and 0 < float(p95_ms) <= 2000, "canary.p95_ms must be > 0 and <= 2000")

    rollback = _passed(data.get("rollback"), "rollback")
    _require(rollback.get("image") == previous_image, "rollback.image must equal previous_image")
    _require(rollback.get("health_status") == PASS, "rollback.health_status must be 'passed'")
    _require(rollback.get("world_room_status") == PASS, "rollback.world_room_status must be 'passed'")
    duration = rollback.get("duration_seconds")
    _require(isinstance(duration, (int, float)) and not isinstance(duration, bool) and 0 < float(duration) <= 300, "rollback.duration_seconds must be > 0 and <= 300")

    return {
        "decision": "GO",
        "candidate_commit": candidate_commit,
        "candidate_image": candidate_image,
        "previous_image": previous_image,
        "observed_at": data["observed_at"],
        "checks": {
            "main_protected": True,
            "health": PASS,
            "world_room": PASS,
            "canary": PASS,
            "rollback": PASS,
        },
    }


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise argparse.ArgumentTypeError("expected true/false")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--main-protected", type=parse_bool, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        _require(isinstance(data, dict), "evidence root must be an object")
        result = validate_evidence(data, expected_commit=args.expected_commit, main_protected=args.main_protected)
    except (OSError, json.JSONDecodeError, GateError) as exc:
        print(json.dumps({"decision": "NO-GO", "reason": str(exc)}, sort_keys=True))
        return 2

    encoded = json.dumps(result, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
