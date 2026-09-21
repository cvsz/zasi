"""Fail-closed validation for production World Room realtime evidence.

This module deliberately validates machine-verifiable fields only. Human-readable
smoke descriptions are useful diagnostics but are never release evidence.
"""

from __future__ import annotations

from typing import Any

MAX_WORLD_ROOM_LATENCY_MS = 5000.0
PASS = "passed"


class WorldRoomEvidenceError(ValueError):
    """Raised when World Room evidence cannot prove a real governed audio turn."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorldRoomEvidenceError(message)


def validate_world_room_realtime(obj: Any, name: str) -> dict[str, Any]:
    """Require explicit proof of a successful realtime audio turn.

    The contract intentionally requires booleans to be exactly ``True`` and a
    positive bounded latency. Missing fields, truthy strings, zero/negative
    latency, and excessive latency all fail closed.
    """
    _require(isinstance(obj, dict), f"{name} must be an object")
    _require(obj.get("status") == PASS, f"{name}.status must be 'passed'")

    for field in (
        "realtime_session_established",
        "audio_sent",
        "audio_response_received",
        "governed_turn_completed",
    ):
        _require(obj.get(field) is True, f"{name}.{field} must be true")

    latency = obj.get("end_to_end_latency_ms")
    _require(
        isinstance(latency, (int, float)) and not isinstance(latency, bool),
        f"{name}.end_to_end_latency_ms must be numeric",
    )
    _require(
        0 < float(latency) <= MAX_WORLD_ROOM_LATENCY_MS,
        f"{name}.end_to_end_latency_ms must be > 0 and <= {int(MAX_WORLD_ROOM_LATENCY_MS)}",
    )
    return obj
