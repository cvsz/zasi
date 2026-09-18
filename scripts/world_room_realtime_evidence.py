#!/usr/bin/env python3
"""Fail-closed validation for real World Room realtime evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class RealtimeEvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RealtimeEvidenceError(message)


def _number(value: Any, name: str) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{name} must be numeric")
    return float(value)


def validate_realtime_phase(obj: Any, name: str) -> None:
    _require(isinstance(obj, dict), f"{name} must be an object")
    _require(obj.get("upstream_configured") is True, f"{name}.upstream_configured must be true")
    _require(obj.get("realtime_session_established") is True, f"{name}.realtime_session_established must be true")
    _require(obj.get("audio_sent") is True, f"{name}.audio_sent must be true")
    _require(obj.get("audio_received") is True, f"{name}.audio_received must be true")
    turns = obj.get("completed_turns")
    _require(isinstance(turns, int) and not isinstance(turns, bool) and turns >= 1, f"{name}.completed_turns must be at least 1")
    latency = _number(obj.get("response_latency_ms"), f"{name}.response_latency_ms")
    _require(0 < latency <= 5000, f"{name}.response_latency_ms must be > 0 and <= 5000")


def validate_realtime_evidence(data: Any) -> None:
    _require(isinstance(data, dict), "evidence root must be an object")
    validate_realtime_phase(data.get("world_room"), "world_room")
    validate_realtime_phase(data.get("rollback"), "rollback")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = json.loads(args.evidence.read_text(encoding="utf-8"))
        validate_realtime_evidence(data)
    except (OSError, json.JSONDecodeError, RealtimeEvidenceError) as exc:
        print(json.dumps({"decision": "NO-GO", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"decision": "GO", "world_room_realtime": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
