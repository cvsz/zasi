#!/usr/bin/env python3
"""Validate the external evidence required before a ZASI production release.

This gate intentionally distinguishes CI rehearsal evidence from real staging evidence.
A release candidate is GO only when repository governance is independently verified
from live GitHub ruleset data and an external staging record proves recent health,
World Room smoke, canary SLOs, and immutable rollback for the exact release candidate.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urlparse

SHA40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+@sha256:[0-9a-f]{64}$")
PASS = "passed"
MAX_EVIDENCE_AGE = timedelta(hours=6)
MAIN_REF_TARGETS = {"~DEFAULT_BRANCH", "refs/heads/main"}
REQUIRED_PRODUCTION_CHECKS = frozenset({
    "Test (Python 3.11)",
    "Test (Python 3.12)",
    "Build Distribution",
    "Docker Build Check",
    "Dependency Review",
    "Python Syntax & React TypeScript Validation",
    "Analyze (actions)",
    "Analyze (javascript-typescript)",
    "Analyze (python)",
    "Build and Security Scan Docker Image",
    "Build security evidence",
    "Clean PostgreSQL backup restore rehearsal",
    "Local two-replica canary and failure rehearsal",
    "Base to candidate to immutable rollback",
    "Validate production GO evidence contract",
})


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
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise GateError(f"{name} is not a valid URL") from exc
    _require(parsed.scheme == "https" and bool(parsed.netloc), f"{name} must be an https URL")
    _require(parsed.hostname is not None, f"{name} must include a hostname")
    try:
        parsed.port
    except ValueError as exc:
        raise GateError(f"{name} has an invalid port") from exc
    _require(parsed.username is None and parsed.password is None, f"{name} must not contain URL credentials")
    _require(parsed.fragment == "", f"{name} must not contain a fragment")
    return value


def _origin(parsed: ParseResult) -> tuple[str, str, int]:
    port = parsed.port if parsed.port is not None else 443
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def _same_origin(value: Any, name: str, staging_url: str) -> str:
    result = _https(value, name)
    parsed = urlparse(result)
    staging = urlparse(staging_url)
    _require(
        _origin(parsed) == _origin(staging),
        f"{name} must use the same origin as staging_url",
    )
    return result


def _timestamp(value: Any, name: str = "observed_at") -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), f"{name} must be an RFC3339 UTC timestamp ending in Z")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateError(f"{name} is not a valid timestamp") from exc
    _require(result.tzinfo is not None, f"{name} must include timezone information")
    return result.astimezone(timezone.utc)


def _phase_timestamp(
    obj: dict[str, Any],
    name: str,
    *,
    previous: datetime | None,
    envelope: datetime,
) -> datetime:
    observed = _timestamp(obj.get("observed_at"), f"{name}.observed_at")
    _require(observed <= envelope, f"{name}.observed_at cannot be after top-level observed_at")
    _require(envelope - observed <= MAX_EVIDENCE_AGE, f"{name}.observed_at is stale relative to the evidence envelope")
    if previous is not None:
        _require(observed >= previous, f"{name}.observed_at must not precede the previous exercise phase")
    return observed


def validate_governance(rulesets: Any) -> dict[str, Any]:
    """Require one active branch ruleset that enforces every #78 main control."""
    _require(isinstance(rulesets, list), "GitHub rulesets evidence must be a list")

    failures: list[str] = []
    for ruleset in rulesets:
        if not isinstance(ruleset, dict):
            continue
        if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
            continue

        ref_name = (ruleset.get("conditions") or {}).get("ref_name") or {}
        includes = ref_name.get("include") or []
        excludes = ref_name.get("exclude") or []
        if not isinstance(includes, list) or not MAIN_REF_TARGETS.intersection(includes):
            continue
        if "refs/heads/main" in excludes or "~DEFAULT_BRANCH" in excludes:
            continue

        rules = ruleset.get("rules")
        if not isinstance(rules, list):
            failures.append(f"ruleset {ruleset.get('id', '<unknown>')} has no expanded rules")
            continue
        by_type = {rule.get("type"): rule for rule in rules if isinstance(rule, dict)}

        missing = sorted({"pull_request", "deletion", "non_fast_forward", "required_status_checks"} - set(by_type))
        if missing:
            failures.append(f"ruleset {ruleset.get('id', '<unknown>')} missing rules: {', '.join(missing)}")
            continue

        pr_params = by_type["pull_request"].get("parameters") or {}
        if pr_params.get("required_review_thread_resolution") is not True:
            failures.append(f"ruleset {ruleset.get('id', '<unknown>')} must require review-thread resolution")
            continue

        status_params = by_type["required_status_checks"].get("parameters") or {}
        required_checks = status_params.get("required_status_checks") or []
        if not isinstance(required_checks, list) or not required_checks:
            failures.append(f"ruleset {ruleset.get('id', '<unknown>')} must require status checks")
            continue
        required_contexts = {
            check.get("context")
            for check in required_checks
            if isinstance(check, dict) and isinstance(check.get("context"), str)
        }
        missing_checks = sorted(REQUIRED_PRODUCTION_CHECKS - required_contexts)
        if missing_checks:
            failures.append(
                f"ruleset {ruleset.get('id', '<unknown>')} missing required production checks: "
                + ", ".join(missing_checks)
            )
            continue
        if status_params.get("strict_required_status_checks_policy") is not True:
            failures.append(f"ruleset {ruleset.get('id', '<unknown>')} must require branch to be up to date")
            continue

        bypass_actors = ruleset.get("bypass_actors") or []
        if bypass_actors:
            failures.append(f"ruleset {ruleset.get('id', '<unknown>')} has bypass actors")
            continue

        return {
            "status": PASS,
            "ruleset_id": ruleset.get("id"),
            "ruleset_name": ruleset.get("name"),
            "required_check_count": len(required_checks),
            "required_production_checks": sorted(REQUIRED_PRODUCTION_CHECKS),
        }

    suffix = f"; candidates rejected: {' | '.join(failures)}" if failures else ""
    raise GateError("no active GitHub ruleset fully protects main with the required production controls" + suffix)


def validate_evidence(
    data: dict[str, Any],
    *,
    expected_commit: str,
    rulesets: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    governance = validate_governance(rulesets)
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

    staging_url = _https(data.get("staging_url"), "staging_url")
    observed_at = _timestamp(data.get("observed_at"))
    current_time = now or datetime.now(timezone.utc)
    _require(current_time.tzinfo is not None, "current time must include timezone information")
    current_time = current_time.astimezone(timezone.utc)
    _require(observed_at <= current_time, "observed_at cannot be in the future")
    _require(current_time - observed_at <= MAX_EVIDENCE_AGE, "staging evidence is stale; observed_at must be within the last 6 hours")

    runtime = _passed(data.get("runtime"), "runtime")
    runtime_at = _phase_timestamp(runtime, "runtime", previous=None, envelope=observed_at)
    _require(runtime.get("inspector") == "docker", "runtime.inspector must be 'docker'")
    _require(runtime.get("observed_image") == candidate_image, "runtime.observed_image must equal candidate_image")

    health = _passed(data.get("health"), "health")
    health_at = _phase_timestamp(health, "health", previous=runtime_at, envelope=observed_at)
    ready_url = _same_origin(health.get("ready_url"), "health.ready_url", staging_url)
    ready = urlparse(ready_url)
    _require(ready.path.rstrip("/") == "/health/ready", "health.ready_url must target /health/ready")
    _require(ready.query == "", "health.ready_url must not contain a query string")
    _require(health.get("observed_commit") == candidate_commit, "health.observed_commit must equal candidate_commit")
    _require(health.get("identity_source") == "artifact", "health.identity_source must be 'artifact'")

    world_room = _passed(data.get("world_room"), "world_room")
    world_room_at = _phase_timestamp(world_room, "world_room", previous=health_at, envelope=observed_at)
    _require(isinstance(world_room.get("smoke_case"), str) and world_room["smoke_case"].strip(), "world_room.smoke_case is required")
    _same_origin(world_room.get("endpoint_url"), "world_room.endpoint_url", staging_url)
    _require(world_room.get("image") == candidate_image, "world_room.image must equal candidate_image")

    canary = _passed(data.get("canary"), "canary")
    canary_at = _phase_timestamp(canary, "canary", previous=world_room_at, envelope=observed_at)
    _same_origin(canary.get("endpoint_url"), "canary.endpoint_url", staging_url)
    _require(canary.get("image") == candidate_image, "canary.image must equal candidate_image")
    request_count = canary.get("request_count")
    error_rate = canary.get("error_rate")
    p95_ms = canary.get("p95_ms")
    _require(isinstance(request_count, int) and not isinstance(request_count, bool) and request_count >= 20, "canary.request_count must be at least 20")
    _require(isinstance(error_rate, (int, float)) and not isinstance(error_rate, bool) and 0 <= float(error_rate) <= 0.01, "canary.error_rate must be between 0 and 0.01")
    _require(isinstance(p95_ms, (int, float)) and not isinstance(p95_ms, bool) and 0 < float(p95_ms) <= 2000, "canary.p95_ms must be > 0 and <= 2000")

    rollback = _passed(data.get("rollback"), "rollback")
    _phase_timestamp(rollback, "rollback", previous=canary_at, envelope=observed_at)
    _same_origin(rollback.get("endpoint_url"), "rollback.endpoint_url", staging_url)
    _require(rollback.get("image") == previous_image, "rollback.image must equal previous_image")
    _require(rollback.get("inspector") == "docker", "rollback.inspector must be 'docker'")
    _require(rollback.get("observed_image") == previous_image, "rollback.observed_image must equal previous_image")
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
        "governance": governance,
        "checks": {
            "main_governance": PASS,
            "freshness": PASS,
            "phase_timeline": PASS,
            "runtime_identity": PASS,
            "health": PASS,
            "world_room": PASS,
            "canary": PASS,
            "rollback": PASS,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--rulesets", type=Path, required=True, help="JSON array of expanded GitHub repository rulesets")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        rulesets = json.loads(args.rulesets.read_text(encoding="utf-8"))
        _require(isinstance(data, dict), "evidence root must be an object")
        result = validate_evidence(data, expected_commit=args.expected_commit, rulesets=rulesets)
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
