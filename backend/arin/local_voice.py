"""ARIN local-first STT/TTS boundary.

This module is deliberately transport/provider neutral. It accepts only an
already-authorized voice perception ticket and local engine callbacks. It has
no cloud fallback, provider credentials, tool/device authority, or actuator
path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

from backend.arin.perception import PerceptionScope, PerceptionSessionTicket


class LocalVoiceDirection(str, Enum):
    STT = "stt"
    TTS = "tts"


@dataclass(frozen=True)
class LocalVoiceRequest:
    tenant_id: str
    session_id: str
    direction: LocalVoiceDirection
    payload: bytes | str


@dataclass(frozen=True)
class LocalVoiceResult:
    tenant_id: str
    session_id: str
    direction: LocalVoiceDirection
    content: bytes | str


def execute_local_voice(
    *,
    request: LocalVoiceRequest,
    ticket: PerceptionSessionTicket,
    now: datetime,
    local_stt: Callable[[bytes], str] | None = None,
    local_tts: Callable[[str], bytes] | None = None,
) -> LocalVoiceResult:
    """Execute one local voice transform after fail-closed ticket validation."""
    if PerceptionScope.VOICE not in ticket.scopes:
        raise PermissionError("voice scope is required")
    if not ticket.is_valid(
        tenant_id=request.tenant_id,
        session_id=request.session_id,
        now=now,
    ):
        raise PermissionError("valid tenant/session-bound voice ticket is required")

    if request.direction is LocalVoiceDirection.STT:
        if not isinstance(request.payload, bytes):
            raise ValueError("STT payload must be bytes")
        if local_stt is None:
            raise RuntimeError("local STT engine unavailable")
        content: bytes | str = local_stt(request.payload)
        if not isinstance(content, str):
            raise ValueError("local STT result must be text")
    elif request.direction is LocalVoiceDirection.TTS:
        if not isinstance(request.payload, str):
            raise ValueError("TTS payload must be text")
        if local_tts is None:
            raise RuntimeError("local TTS engine unavailable")
        content = local_tts(request.payload)
        if not isinstance(content, bytes):
            raise ValueError("local TTS result must be bytes")
    else:
        raise ValueError("unsupported local voice direction")

    return LocalVoiceResult(
        tenant_id=request.tenant_id,
        session_id=request.session_id,
        direction=request.direction,
        content=content,
    )
